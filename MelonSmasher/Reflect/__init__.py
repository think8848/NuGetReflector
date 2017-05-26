from __future__ import print_function

from lxml import objectify
from time import sleep
from requests import put, get
from subprocess import call
import os.path
import sys
import hashlib
import base64

NAME_SCHEME_META = '{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}'
NAME_SCHEME_DATA = '{http://schemas.microsoft.com/ado/2007/08/dataservices}'
KEY_PROPERTIES = ''.join([NAME_SCHEME_META, 'properties'])
KEY_VERSION = ''.join([NAME_SCHEME_DATA, 'Version'])
KEY_HASH = ''.join([NAME_SCHEME_DATA, 'PackageHash'])
KEY_ALGORITHM = ''.join([NAME_SCHEME_DATA, 'PackageHashAlgorithm'])
KEY_TITLE = 'title'
KEY_CONTENT = 'content'
KEY_SRC = 'src'
KEY_REL = 'rel'
KEY_HREF = 'href'
VALUE_NEXT = 'next'


class Mirror(object):
    def __init__(self,
                 remote_url,
                 local_url,
                 package_storage_path,
                 local_api_key,
                 dotnet_path,
                 verify_downloads=True,
                 verify_uploaded=True,
                 verify_cache=False
                 ):
        """
        :param remote_url: 
        :param local_url: 
        :param package_storage_path: 
        :param local_api_key: 
        :param dotnet_path: 
        :param verify_downloads: 
        :param verify_uploaded: 
        :param verify_cache: 
        """
        self.remote_api_url = '/'.join([remote_url, 'api/v2'])
        self.remote_packages_url = '/'.join([self.remote_api_url, 'Packages'])
        self.local_api_url = '/'.join([local_url, 'api/v2'])
        self.local_api_upload_url = '/'.join([self.local_api_url, 'package'])
        self.local_packages_url = '/'.join([self.local_api_url, 'Packages'])
        self.package_storage_path = package_storage_path
        self.local_api_key = local_api_key
        self.dotnet_path = dotnet_path
        self.verify_downloads = verify_downloads
        self.verify_uploaded = verify_uploaded
        self.verify_cache = verify_cache

    @staticmethod
    def hash_bytestr_iter(bytesiter, hasher, ashexstr=False):
        for block in bytesiter:
            hasher.update(block)
        return hasher.hexdigest() if ashexstr else hasher.digest()

    @staticmethod
    def file_as_blockiter(file, blocksize=65536):
        with file:
            block = file.read(blocksize)
            while len(block) > 0:
                yield block
                block = file.read(blocksize)

    def sha512sum(self, file_path, blocksize=65536):
        """
        :param file_path: 
        :param blocksize: 
        :return: 
        """
        return base64.encodestring(
            self.hash_bytestr_iter(self.file_as_blockiter(open(file_path, 'rb')), hashlib.sha512(), False)).replace(
            "\n", '')

    def sha256sum(self, file_path, blocksize=65536):
        """
        :param file_path: 
        :param blocksize: 
        :return: 
        """
        return base64.encodestring(
            self.hash_bytestr_iter(self.file_as_blockiter(open(file_path, 'rb')), hashlib.sha256(), False)).replace(
            "\n", '')

    @staticmethod
    def hashes_match(hash_1, hash_2):
        """
        :param hash_1: 
        :param hash_2: 
        :return: 
        """
        if str(hash_1) == str(hash_2):
            print(' Pass!')
            return True
        else:
            print(' Fail!')
            print('Hash 1: ' + hash_1)
            print('Hash 2: ' + hash_2)
            return False

    def verify_package_hash(self, file_path, target_hash, message='Verifying package hash...'):
        """
        :param file_path: 
        :param target_hash: 
        :param message: 
        :return: 
        """
        sys.stdout.write(message)
        sys.stdout.flush()
        local_hash = self.sha512sum(file_path)
        return self.hashes_match(local_hash, target_hash)

    @staticmethod
    def _get(url):
        """
        :param url: str
        :return: objectify.ObjectifiedElement | bool
        """
        response = get(url)
        if response.status_code == 200:
            xml = response.content
            try:
                response.objectified = objectify.fromstring(xml)
                return response
            except Exception as e:
                print(e.message)
                return False
        else:
            return response

    def local_package(self, title, version):
        """
        :param title: 
        :param version: 
        :return: 
        """
        url = ''.join([self.local_packages_url, '(Id=\'', title, '\',Version=\'', version, '\')'])
        return self._get(url)

    def remote_package(self, title, version):
        """
        :param title: 
        :param version: 
        :return: 
        """
        url = ''.join([self.remote_packages_url, '(Id=\'', title, '\',Version=\'', version, '\')'])
        return self._get(url)

    def local_packages(self, url=None):
        """
        :param url: 
        :return: 
        """
        if url is None: url = self.local_packages_url
        return self._get(url)

    def remote_packages(self, url=None):
        """
        :param url: 
        :return: 
        """
        if url is None: url = self.remote_packages_url
        return self._get(url)

    def _download_package(self, content_url, local_path, remote_hash=None, reties=0, force=False):
        """
        :param content_url: 
        :param local_path: 
        :param remote_hash: 
        :param reties: 
        :param force: 
        :return: 
        """
        if not os.path.isfile(local_path) or force:
            count = 0
            sys.stdout.write('Downloading package.')
            sys.stdout.flush()
            # Get the file and stream it to the disk
            r = get(content_url, stream=True)
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        # Count the chunks
                        count = count + 1
                        if count >= 10000:
                            # Write a dot every 10000 chunks
                            sys.stdout.write('.')
                            sys.stdout.flush()
                        # Write to the file when the chunk gets to 1024
                        f.write(chunk)
                        f.flush()
            print('')

        if os.path.isfile(local_path):
            if not remote_hash is None:
                hash_verified = self.verify_package_hash(local_path, remote_hash)
                if not hash_verified and reties < 3:
                    # Retry loop
                    reties += 1
                    print('Hashes do not match retrying download...')
                    return self._download_package(content_url, local_path, remote_hash, reties, True)
                elif not hash_verified and reties >= 3:
                    # Reached max retries
                    print('Retried to download the package 3 times, moving on... :-(')
                    return False
                else:
                    # Hash verified
                    return True
            else:
                # Skipping hash verification
                return True
        else:
            # File did not exists after DL
            return False

    def _upload_package(self, local_path, title, version, force=False):
        """
        :param local_path: 
        :param title: 
        :param version: 
        :param force: 
        :return: 
        """
        local_response = self.local_package(title, version)
        if local_response.status_code == 404 or force:
            print('Uploading package...')
            cmd = ' '.join([self.dotnet_path, 'nuget', 'push', local_path, '-s', self.local_api_upload_url, '-k',
                            self.local_api_key])
            return_code = call(cmd, shell=True)
            upload_status = {
                'response': return_code,
                'mirrored': True,
                'uploaded': True
            }
        elif local_response.status_code == 200:
            print('Package already mirrored...')
            upload_status = {
                'response': local_response,
                'mirrored': True,
                'uploaded': False,
                'server_hash': local_response.objectified[KEY_PROPERTIES][KEY_HASH]
            }
        else:
            return {
                'response': local_response,
                'mirrored': False,
                'uploaded': False,
                'server_hash': False
            }

        if not 'server_hash' in upload_status and self.verify_uploaded:
            r = self.local_package(title, version)
            if r.status_code == 200:
                upload_status['server_hash'] = r.objectified[KEY_PROPERTIES][KEY_HASH]
            else:
                upload_status['server_hash'] = False

        return upload_status

    def sync_and_verify_package(self, package, retry=0):
        """
        :param package: 
        :return: 
        """
        # Extract the info that we need from the entry
        title = str(package[KEY_TITLE])
        version = str(package[KEY_PROPERTIES][KEY_VERSION])
        package_name = '.'.join([title, version])
        content_url = package[KEY_CONTENT].get(KEY_SRC)
        local_path = os.path.join(self.package_storage_path, '.'.join([package_name, 'nupkg']))
        remote_hash = str(package[KEY_PROPERTIES][KEY_HASH]) if self.verify_downloads else None
        dl_status = False
        up_status = {}

        # Begin package sync
        print('')
        print(''.join(['########## ', package_name, ' ##########']))

        if not os.path.isfile(local_path):
            dl_status = self._download_package(content_url, local_path, remote_hash)
        else:
            if self.verify_cache:
                if not self.verify_package_hash(local_path, remote_hash):
                    os.remove(local_path)
                    dl_status = self._download_package(content_url, local_path, remote_hash, True)
                else:
                    dl_status = True

        if dl_status:
            up_status = self._upload_package(local_path, title, version)
            if up_status['mirrored']:
                if self.verify_uploaded and up_status['server_hash']:
                    sys.stdout.write('Verifying server hashes...')
                    sys.stdout.flush()
                    if not self.hashes_match(remote_hash, up_status['server_hash']):
                        print('Mirror and repo hashes do not match! Re-uploading...')
                        up_status = self._upload_package(local_path, title, version, True)
                        if not self.hashes_match(remote_hash, up_status['server_hash']):
                            if retry < 3:
                                retry += 1
                                up_status = self.sync_and_verify_package(package, retry)
                            else:
                                print('Max sync retries reached! Moving on...')
                                return up_status

                if up_status['uploaded']:
                    print('Package uploaded!')

                if not up_status['uploaded']:
                    print('Package already uploaded!')
            else:
                # print(''.join(['Response Body: ', up_status['response'].text]))
                print('Package not mirrored!')
        else:
            up_status = {
                'response': None,
                'mirrored': False,
                'uploaded': False,
                'server_hash': False
            }
        print('')
        return up_status

    def sync_packages(self):
        """        
        :return: 
        """
        done = False
        url = self.remote_packages_url
        while not done:
            # print(''.join(['Requesting packages from: ', url]))
            response = self.remote_packages(url)
            if response.status_code == 200:
                page = response.objectified
                # print(''.join(['Remote API returned: ', str(len(page.entry)), ' packages!']))
                # Whats the size of the entry list
                if len(page.entry) > 0:
                    for package in page.entry:
                        self.sync_and_verify_package(package)
                # Get the last link on the page
                link = page.link[0] if 0 > (len(page.link) - 1) else page.link[(len(page.link) - 1)]
                # If the last link is the next link set it's url as the target url for the next iteration
                if link.get(KEY_REL) == VALUE_NEXT:
                    url = link.get(KEY_HREF)
                else:
                    # Break out
                    done = True
            else:
                print('Received bad http code from remote API. Sleeping for 10 and trying again. Response Code: ' + str(
                    response.status_code))
                sleep(10)
        return True
