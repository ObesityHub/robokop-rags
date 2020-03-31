
from rags_src.util import Text, LoggingUtil

from typing import NamedTuple

import logging

logger = LoggingUtil.init_logging(__name__, level=logging.DEBUG)


class KNode(object):

    def __init__(self, id: str, type: str, name: str = None, properties: dict = {}):
        self.id = id
        self.type = type
        self.name = name
        self.properties = properties

        # Synonyms are a list of synonymous curies
        self.synonyms = set()
        self.synonyms.add(LabeledID(identifier=id, label=name))

    def add_synonyms(self, new_synonym_set):
        self.synonyms.update(new_synonym_set)

    def get_synonyms_by_prefix(self, prefix):
        """Returns curies (not labeledIDs) for any synonym with the input prefix"""
        return set( filter(lambda x: Text.get_curie(x).upper() == prefix.upper(), [s.identifier for s in self.synonyms]) )

    def get_labeled_ids_by_prefix(self, prefix):
        """Returns labeledIDs for any synonym with the input prefix"""
        return set( filter(lambda x: Text.get_curie(x.identifier).upper() == prefix.upper(), self.synonyms) )

    def __repr__(self):
        # return "KNode(id={0},type={1})".format (self.id, self.type)
        return "N({0},t={1})".format(self.id, self.type)

    def __str__(self):
        return self.__repr__()

    # Is using identifier sufficient?  Probably need to be a bit smarter.
    def __hash__(self):
        """Class needs __hash__ in order to be used as a node in networkx"""
        return self.id.__hash__()

    def __eq__(self, other):
        if isinstance(self, int) or isinstance(other, int):
            return False
        return self.id == other.id

    def get_shortname(self):
        """Return a short user-readable string suitable for display in a list"""
        if self.name is not None:
            return '%s (%s)' % (self.name, self.id)
        return self.id

    def n2json(self):
        """ Serialize a node as json. """
        return {
            "id": self.id,
            "type": f"blm:{self.type}",
        }


class KEdge(object):
    """Used as the edge object in KnowledgeGraph.

    Instances of this class should be returned from greenT"""

    def __init__(self,
                 source_id: str,
                 target_id: str,
                 provided_by: str,
                 ctime: int,
                 namespace: str,
                 project_id: str,
                 project_name: str,
                 original_predicate: str,
                 standard_predicate: str,
                 url: str = "",
                 input_id: str = "",
                 publications: list = [],
                 properties: dict = {}):
        self.source_id = source_id
        self.target_id = target_id
        self.provided_by = provided_by
        self.ctime = ctime
        self.namespace = namespace
        self.project_id = project_id
        self.project_name = project_name
        self.original_predicate = original_predicate
        self.standard_predicate = standard_predicate
        self.publications = publications
        self.url = url
        self.properties = properties

    def load_attribute(self, key, value):
        if key == 'original_predicate' or key == 'standard_predicate':
            return LabeledID(**value) if isinstance(value, dict) else value
        else:
            return super().load_attribute(key, value)

    def __key(self):
        return (self.source_id, self.target_id, self.provided_by, self.original_predicate, self.project_id, self.namespace)

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __lt__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __hash__(self):
        return hash(self.__key())

    def long_form(self):
        return "E(src={0},subjn={1},objn={2})".format(self.provided_by, self.source_id, self.target_id)

    def __repr__(self):
        return self.long_form()

    def __str__(self):
        return self.__repr__()

    def e2json(self):
        """ Serialize an edge as json. """
        return {
            "ctime": str(self.ctime),
            "sub": self.source_id,
            "pred": self.standard_predicate,
            "obj": self.target_id,
            "pubs": str(self.publications)
        }


class LabeledID(NamedTuple):
    identifier: str
    label: str = ''

    def __repr__(self):
        return f'({self.identifier},{self.label})'

    def __gt__(self, other):
        return self.identifier > other.identifier
