# Copyright 2005-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# Author(s): Nicholas Carpaski (carpaski@gentoo.org), Brian Harring (ferringb@gentoo.org)

__all__ = ["cache"]

import stat
import sys
import operator
from portage.util import normalize_path
import errno
from portage.exception import PermissionDenied
from portage import os
from portage import checksum

if sys.hexversion >= 0x3000000:
	long = int


class hashed_path(object):

	def __init__(self, location):
		self.location = location

	def __getattr__(self, attr):
		if attr == 'mtime':
			# use stat.ST_MTIME; accessing .st_mtime gets you a float
			# depending on the python version, and long(float) introduces
			# some rounding issues that aren't present for people using
			# the straight c api.
			# thus use the defacto python compatibility work around;
			# access via index, which gurantees you get the raw long.
			self.mtime = obj = os.stat(self.location)[stat.ST_MTIME]
			return obj
		if not attr.islower():
			# we don't care to allow .mD5 as an alias for .md5
			raise AttributeError(attr)
		try:
			val = checksum.perform_checksum(self.location, attr.upper())[0]
		except KeyError:
			raise AttributeError(attr)
		setattr(self, attr, val)
		return val


class cache(object):
	"""
	Maintains the cache information about eclasses used in ebuild.
	"""
	def __init__(self, porttree_root, overlays=[]):

		self.eclasses = {} # {"Name": hashed_path}
		self._eclass_locations = {}

		# screw with the porttree ordering, w/out having bash inherit match it, and I'll hurt you.
		# ~harring
		if porttree_root:
			self.porttree_root = porttree_root
			self.porttrees = [self.porttree_root] + overlays
			self.porttrees = tuple(map(normalize_path, self.porttrees))
			self._master_eclass_root = os.path.join(self.porttrees[0], "eclass")
			self.update_eclasses()
		else:
			self.porttree_root = None
			self.porttrees = ()
			self._master_eclass_root = None

	def copy(self):
		return self.__copy__()

	def __copy__(self):
		result = self.__class__(None)
		result.eclasses = self.eclasses.copy()
		result._eclass_locations = self._eclass_locations.copy()
		result.porttree_root = self.porttree_root
		result.porttrees = self.porttrees
		result._master_eclass_root = self._master_eclass_root
		return result

	def append(self, other):
		"""
		Append another instance to this instance. This will cause eclasses
		from the other instance to override any eclasses from this instance
		that have the same name.
		"""
		if not isinstance(other, self.__class__):
			raise TypeError(
				"expected type %s, got %s" % (self.__class__, type(other)))
		self.porttrees = self.porttrees + other.porttrees
		self.eclasses.update(other.eclasses)
		self._eclass_locations.update(other._eclass_locations)

	def update_eclasses(self):
		self.eclasses = {}
		self._eclass_locations = {}
		master_eclasses = {}
		eclass_len = len(".eclass")
		ignored_listdir_errnos = (errno.ENOENT, errno.ENOTDIR)
		for x in [normalize_path(os.path.join(y,"eclass")) for y in self.porttrees]:
			try:
				eclass_filenames = os.listdir(x)
			except OSError as e:
				if e.errno in ignored_listdir_errnos:
					del e
					continue
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(x)
				raise
			for y in eclass_filenames:
				if not y.endswith(".eclass"):
					continue
				obj = hashed_path(os.path.join(x, y))
				obj.eclass_dir = x
				try:
					mtime = obj.mtime
				except OSError:
					continue
				ys=y[:-eclass_len]
				if x == self._master_eclass_root:
					master_eclasses[ys] = mtime
					self.eclasses[ys] = obj
					self._eclass_locations[ys] = x
					continue

				master_mtime = master_eclasses.get(ys)
				if master_mtime is not None:
					if master_mtime == mtime:
						# It appears to be identical to the master,
						# so prefer the master entry.
						continue

				self.eclasses[ys] = obj
				self._eclass_locations[ys] = x

	def validate_and_rewrite_cache(self, ec_dict, chf_type, stores_paths):
		if not isinstance(ec_dict, dict):
			return None
		our_getter = operator.attrgetter(chf_type)
		cache_getter = lambda x:x
		if stores_paths:
			key_getter = operator.itemgetter(1)
		d = {}
		for eclass, ec_data in ec_dict.items():
			cached_data = self.eclasses.get(eclass)
			if cached_data is None:
				return None
			if cache_getter(ec_data) != our_getter(cached_data):
				return None
			d[eclass] = cached_data
		return d

	def get_eclass_data(self, inherits):
		ec_dict = {}
		for x in inherits:
			ec_dict[x] = self.eclasses[x]

		return ec_dict
