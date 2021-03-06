from os import makedirs
from os.path import sep, exists, isfile, splitext, basename, join, dirname
from pyrus.checksum import hexdigest
from abc import abstractproperty, ABCMeta
from tempfile import mkdtemp

required_checksums = ['md5', 'sha1', 'sha256', 'sha512']

def import_module(fqn):
	"""Helper method for dynamic import of modules based on full qualified name.
	Eg: fqn = 'jsnoop.handlers.manifest'
	"""
	mod = __import__(fqn)
	for comp in fqn.split('.')[1:]:
		mod = getattr(mod, comp)
	return mod

# Module prefix to make things cleaner
__MODULE_PREFIX = 'jsnoop.handlers'

# Default fall back handler
__DEFAULT_MODULE = 'simplefile'

# Mapping between module names and containted handler classes
__CLASSES = {
	'archivefile'	: 'ArchiveFile',
	'javaclass'	: 'ClassFile',
	'manifest'	: 'ManifestFile',
	'signature'	: 'SignatureFile',
	'simplefile'	: 'SimpleFile'
}

# Mapping of file extensions and handler modules
# File extensions are to be in lovercase with preceding '.' intact
__MODULES = {
	'.mf'	: 'manifest',
	'.rsa'	: 'signature',
	'.dsa'	: 'signature',
	'.class': 'javaclass',
	'.zip'	: 'archivefile',
	'.gz'	: 'archivefile',
	'.bz2'	: 'archivefile',
	'.tar'	: 'archivefile',
	'.jar'	: 'archivefile',
	'.war'	: 'archivefile',
	'.sar'	: 'archivefile',
	'.war'	: 'archivefile'
}

def get_known_extensions():
	"""Returns a list of extensions that the package knows about."""
	return list(__MODULES.keys())

__IGNORED_EXTENSIONS = []
def ignore_extensions(arg):
	"""Add either an extension or a list of extensions to the ignore lis. This
	means that if we know of a handler for this type, we will ignore that and
	handler using a simple file handler. If you want to ignore it completely,
	you will have to implement that logic in your application. You can make use
	of the ignored_extensions() method."""
	exts = [arg] if isinstance(arg, str) else arg
	exts = [ext.lower() for ext in exts]
	__IGNORED_EXTENSIONS += exts

def unignore_extensions(arg):
	"""This method removes an extension or a list of extensions from the current
	list of extensions if it exist."""
	exts = [arg] if isinstance(arg, str) else arg
	exts = [ext.lower() for ext in exts]
	for ext in exts:
		if ext in __IGNORED_EXTENSIONS:
			__IGNORED_EXTENSIONS.remove(ext)

def ignored_extensions():
	"""Returns a list of extensions we ignore."""
	return __IGNORED_EXTENSIONS

def is_ignored_extension(ext):
	"""Returns true if the given extension is being ignored."""
	return ext.lower() in __IGNORED_EXTENSIONS

# Dictionary to cache loaded clases, saves work for repeated loads
__LOADED = {}

def __handler_class(module):
	"""Internal method to assist in loading the correct class giving a module's
	basename. A call to this method returns the class if its already loaded else
	loads it, marks it as loaded then returns it.

	Do not use this method unless you know what you are doing."""
	klass = __CLASSES.get(module)
	module = '%s.%s' % (__MODULE_PREFIX, module)
	fqn = '%s.%s' % (module, klass)
	if fqn not in __LOADED:
		__LOADED[fqn] = getattr(import_module(module), klass)
	return __LOADED[fqn]

def get_handler(filename):
	"""Method to get the correct handler class based on file's extension."""
	try:
		extension = splitext(filename)[-1].lower()
		if is_ignored_extension(extension):
			module = __DEFAULT_MODULE
		else:
			module = __MODULES.get(extension, __DEFAULT_MODULE)
	except:
		module = __DEFAULT_MODULE
	return __handler_class(module)

def get_handler_obj(filepath, fileobj=None, parent_path='', parent_sha512=None):
	"""Method to create an instance of the correct handler class based on
	filepath. We first would try to unpack it using brute force, if not possible
	find the next best handler by extracting the file extension."""
	try:
		# force try handling as an archive (we want to go as deep as possible)
		handler = __handler_class('archivefile')(filepath, fileobj,
							parent_path, parent_sha512)
	except ValueError:
		handler = get_handler(filepath)
		handler = handler(filepath, fileobj, parent_path, parent_sha512)
	return handler

class AbstractFile(metaclass=ABCMeta):
	def __init__(self, filepath, fileobj=None, parent_path='',
				parent_sha512=None):
		self.filepath = filepath
		self.fileobj = fileobj
		self.path = dirname(filepath.replace(parent_path, '').lstrip(sep))
		self.name = basename(filepath)
		self.type = splitext(filepath)[-1].lower()
		self.parent = parent_sha512
		self.persist()
		# Use filebytes given, as this maybe in memory processing
		self.prepare_checksums()

	@abstractproperty
	def inmemory(self):
		return True

	@property
	def filepath(self):
		if self.__ondisk is None:
			return self.__filepath
		else:
			return self.__ondisk

	@filepath.setter
	def filepath(self, value):
		self.__filepath = value

	def persist(self):
		# We use a separate internal property to handle deletion when the
		# filepath is actually valid
		self.__ondisk = None
		if self.fileobj is not None and not self.inmemory:
			temp_dir = mkdtemp(prefix='jsnoop.file.persist.')
			temp_file = join(temp_dir, self.filepath)
			makedirs(dirname(temp_file))
			self.fileobj.seek(0)
			with open(temp_file, 'wb') as f:
				f.write(self.fileobj.read())
				self.fileobj.seek(0)
			self.__ondisk = temp_file

	def __del__(self):
		try:
			if self.__ondisk:
				from shutil import rmtree
				rmtree(self.__ondisk.replace(self.__filepath, ''))
		except:
			pass

	def prepare_checksums(self):
		if not self.fileobj:
			# If we are given a filepath make sure if its a valid file
			assert exists(self.filepath) and isfile(self.filepath)
			fileinput = self.filepath
		else:
			fileinput = self.fileobj
		self.checksums = {}
		for algorithm in required_checksums:
			self.checksums[algorithm] = hexdigest(fileinput, algorithm)

	def info(self):
		fileinfo = {}
		fileinfo['path'] = self.path
		fileinfo['name'] = self.name
		fileinfo['type'] = self.type
		fileinfo['parent'] = self.parent
		fileinfo['handler'] = self.__class__.__name__
		for key in self.checksums:
			fileinfo[key] = self.checksums[key]
		return fileinfo
