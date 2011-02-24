# Copyright (c) 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.

from iniparse import ConfigParser
import os

class Repo(dict):
    '''
    Holder object for repo data. Upon instantiation, the instance will be populated with
    default values. When the repo is sent to the RepoFile (either through add_repo or
    update_repo), the current values in a Repo instance will be written to the
    underlying store.

    Repo-specific values are set using dict notation with the exception of the URL for
    the repo. This is done through the set_repo_urls method.
    '''

    # Default properties in the form: (name, default_value)
    # This list does not contain 'baseurl' or 'mirrorlist' since we can only have
    # one of them present in a repo at any time and defaulting them will cause their
    # presence in the generated repo file. Special handling will be done in
    # the items() call to add in whichever is present.
    PROPERTIES = (
        ('name', None),
        ('enabled', '1'),
        ('gpgkey', None),
        ('sslverify', '0'),
        ('gpgcheck', '0'),
    )

    def __init__(self, id):
        '''
        Creates a new instance, populating itself with the default values for all
        properties defined in PROPERTIES.

        @param id: unique identifier for the repo
        @type  id: string
        '''
        self.id = id
        for k, d in self.PROPERTIES:
            self[k] = d

    def items(self):
        '''
        Returns a list of relevant key/value pairs set for this instance.

        @return: list of key/value pairs describing the repo
        @rtype:  list of tuples; (string, string)
        '''
        lst = []
        for k, d in self.PROPERTIES:
            v = self.get(k)
            lst.append((k, v))

        # Since we'll have either baseurl or mirrorlist, keep them out of
        # PROPERTIES and do explicit handling here.
        if 'baseurl' in self:
            lst.append(('baseurl', self.get('baseurl')))
        if 'mirrorlist' in self:
            lst.append(('mirrorlist', self.get('mirrorlist')))

        return tuple(lst)

    def __str__(self):
        s = []
        s.append('[%s]' % self.id)
        for k, v in self.items():
            s.append('%s = %s' % (k, v))
        return '\n'.join(s)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


class RepoFile(object):
    '''
    Represents a .repo file, including operations to manipulate its repositories and
    CRUD operations on the file itself.
    '''

    # Be careful when changing the spacing below, the parser takes issue when the comment
    # indicator isn't in the first column. The blank line at the end is fine though.
    FILE_HEADER = '''#
# Pulp Repositories
# Managed by Pulp client
#

'''

    def __init__(self, filename):
        '''
        @param filename: absolute path to the repo file; the repo file does not need to
                         exist at the time of instantiation, the save method will write it
                         out if it doesn't
        @type  filename: string; may not be None

        @raise ValueError: if filename is missing
        '''
        if filename is None:
            raise ValueError('Filename must be specified when creating a RepoFile')

        self.filename = filename
        self.parser = ConfigParser()

    # -- file manipulation ------------------------------------------------------------

    def delete(self):
        '''
        If the repo file exists, it will be deleted. If not, this method does nothing.

        @raise Exception: if there is an error during the delete
        '''
        if os.path.exists(self.filename):
            os.unlink(self.filename)

    def load(self, allow_missing=True):
        '''
        Loads the repo file.

        @param allow_missing: if True, this call will not throw an error if the file cannot
                              be found; defaults to True
        @type  allow_missing: bool

        @raise Exception: if there is an error during the read
        '''
        if allow_missing and not os.path.exists(self.filename):
            return

        r = Reader(self.filename)
        self.parser.readfp(r)

    def save(self):
        '''
        Saves the current repositories to the repo file.

        @raise Exception: if there is an error during the write
        '''
        # If the file doesn't exist, initialize with Pulp header
        first_write = not os.path.exists(self.filename)

        f = open(self.filename, 'w')

        if first_write:
            f.write(RepoFile.FILE_HEADER)

        # Write the contents of the parser
        self.parser.write(f)
        
        f.close()

    # -- contents manipulation ------------------------------------------------------------

    def add_repo(self, repo):
        '''
        Adds a new repo to this object, however the file is not saved.

        This is not saved as an object reference, so future changes to the passed in
        repo will not be captured in this RepoFile instance. If changes are made to
        the original Repo object, it must be passed into the RepoFile instance through
        update_repo in order for the changes to be captured.

        @param repo: repo to add; may not be None
        @type  repo: L{Repo}
        '''
        self.parser.add_section(repo.id)
        self._repo_to_parser(repo)

    def remove_repo_by_name(self, repo_name):
        '''
        Removes the repo with the given name. If the repo does not exist, this
        method does nothing.

        @param repo: identifies the repo to remove
        @type  repo: string
        '''
        return self.parser.remove_section(repo_name)

    def update_repo(self, repo):
        '''
        Updates the underlying store with the latest contents of a repo. The repo
        passed to this method must have been created prior to this call.

        The repo is not saved as an object reference. Instead, the values are captured
        to the underlying store at the point in time this is called.

        @param repo: repo instance containing updated values to store; cannot be None
        @type  repo: L{Repo}
        '''
        self._repo_to_parser(repo)
        
    def get_repo(self, repo_name):
        '''
        Loads a repo by name. If the repo does not exist, returns None.

        @param repo_name: name of the repo to retrieve
        @type  repo_name: string

        @return: repo instance if one exists; None otherwise
        @rtype:  L{Repo}
        '''
        if self.parser.has_section(repo_name):
            repo = self._parser_to_repo(repo_name)
            return repo
        else:
            return None

    def all_repos(self):
        '''
        Returns a list of all repos in the store.

        @return: list of repo instances; empty list if there are none
        @rtype:  list of L{Repo}
        '''
        repos = []
        for repo_name in self.parser.sections():
            repo = self._parser_to_repo(repo_name)
            repos.append(repo)

        return repos

    def _repo_to_parser(self, repo):
        '''
        Adds the contents of the repo to the underlying store. This call assumes
        the parser section has already been created.

        @param repo: repo instance to update in the parser; cannot be None
        @type  repo: L{Repo}
        '''
        for k, v in repo.items():
            if v:
                self.parser.set(repo.id, k, v)
            else:
                self.parser.remove_option(repo.id, k)

    def _parser_to_repo(self, repo_name):
        '''
        Utility for converting the config parser section into a repo object.

        @param repo_name: name of the repo being retrieved from the store
        @type  repo_name: string

        @return: repo instance populated from the section data
        @rtype:  L{Repo}
        '''
        repo = Repo(repo_name)
        for key, value in self.parser.items(repo_name):
            repo[key] = value

        return repo

class MirrorListFile(object):
    '''
    This is a similar abstraction as RepoFile is. It represents a single local mirror
    list file, regardless of whether or not the file has been saved yet. The usage is
    to create the instance, specifying the filename to which it will be written,
    populate the entries, and save the file.
    '''

    def __init__(self, filename):
        '''
        @param filename: absolute path to the repo file; the repo file does not need to
                         exist at the time of instantiation, the save method will write it
                         out if it doesn't
        @type  filename: string; may not be None

        @raise ValueError: if filename is missing
        '''
        if filename is None:
            raise ValueError('Filename must be specified when creating a MirrorListFile')

        self.filename = filename
        self.entries = []

    def add_entry(self, url):
        '''
        Adds a new entry in this mirror list.

        @param url: repo URL to be added to the mirror list; cannot be None
        @type  url: string
        '''
        self.entries.append(url)

    def add_entries(self, url_list):
        '''
        Adds all entries in the given list to this mirror list

        @param url_list: list of URLs to add
        @type  url_list: list
        '''
        self.entries.extend(url_list)
        
    def delete(self):
        '''
        If the mirror list file exists, it will be deleted. If not, this method does nothing.

        @raise Exception: if there is an error during the delete
        '''
        if os.path.exists(self.filename):
            os.unlink(self.filename)

    def load(self):
        '''
        Loads the contents of the mirror list from the file into this instance. This
        will overwrite any entries already in this instance.

        @raise Exception: if the file cannot be read
        '''
        f = open(self.filename, 'r')
        entries = f.read()
        self.entries = entries.split()
        f.close()
        
    def save(self):
        '''
        Writes the entries in this instance out to the file.

        @raise Exception: if there is an error during the save
        '''
        f = open(self.filename, 'w')
        for entry in self.entries:
            f.write(entry)
            f.write('\n')
        f.close()

class Reader(object):
    '''
    Reader object used to mitigate annoying behavior of iniparse of leaving blank
    lines when removing sections.
    '''

    def __init__(self, path):
        '''
        @param path: the absolute path to a .repo file
        @type  path: str
        '''
        f = open(path)
        bfr = f.read()
        self.idx = 0
        self.lines = bfr.split('\n')
        f.close()

    def readline(self):
        '''
        Read the next line. Strips annoying blank lines left by iniparse when
        removing sections.

        @return: next line or None
        @rtype:  str or None
        '''
        nl = 0
        ln = None
        i = self.idx
        eof = len(self.lines)
        while 1:
            if i == eof:
                return
            ln = self.lines[i]
            i += 1
            if not ln:
                nl += 1
            else:
                break
        if nl:
            i -= 1
            ln = '\n'
        self.idx = i
        return ln

