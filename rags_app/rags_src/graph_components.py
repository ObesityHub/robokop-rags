
from rags_src.util import Text

from typing import NamedTuple


class KNode(object):

    def __init__(self, id: str, type: str, name: str = None, properties: dict = None):
        self.id = id
        self.type = type
        self.name = name
        self.properties = properties if properties else {}

        # Synonyms are a list of synonymous curies
        self.synonyms = set()
        self.synonyms.add(id)

    def add_synonyms(self, new_synonym_set):
        self.synonyms.update(new_synonym_set)

    def get_synonyms_by_prefix(self, prefix):
        """Returns curies for any synonym with the input prefix"""
        return set( filter(lambda x: Text.get_curie(x).upper() == prefix.upper(), self.synonyms) )

    def __repr__(self):
        # return "KNode(id={0},type={1})".format (self.id, self.type)
        return "N({0},t={1})".format(self.id, self.type)

    def __str__(self):
        return self.__repr__()

    def __hash__(self):
        return self.id.__hash__()

    def __eq__(self, other):
        if isinstance(self, int) or isinstance(other, int):
            return False
        return self.id == other.id


class KEdge(object):

    def __init__(self,
                 source_id: str,
                 target_id: str,
                 provided_by: str,
                 input_id: str,
                 ctime: int,
                 original_predicate: str,
                 standard_predicate: str,
                 namespace: str,
                 project_id: str,
                 project_name: str,
                 url: str = "",
                 publications: list = None,
                 properties: dict = None):
        self.namespace = namespace
        self.project_id = project_id
        self.project_name = project_name
        self.source_id = source_id
        self.target_id = target_id
        self.provided_by = provided_by
        self.input_id = input_id
        self.ctime = ctime
        self.original_predicate = original_predicate
        self.standard_predicate = standard_predicate
        self.publications = publications if publications else []
        self.properties = properties if properties else {}
        self.url = url

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


class LabeledID(NamedTuple):
    identifier: str
    label: str = ''

    def __repr__(self):
        return f'({self.identifier},{self.label})'

    def __gt__(self, other):
        return self.identifier > other.identifier
