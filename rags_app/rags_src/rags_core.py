from collections import defaultdict
from dataclasses import dataclass, field
from rags_src.util import Text

# constants that correspond to node types in the biolink model
TESTING_NODE = 'rags:Testing'
CHEMICAL_SUBSTANCE = 'biolink:ChemicalSubstance'
DISEASE = 'biolink:Disease'
GENE = 'biolink:Gene'
PHENOTYPIC_FEATURE = 'biolink:PhenotypicFeature'
DISEASE_OR_PHENOTYPIC_FEATURE = 'biolink:DiseaseOrPhenotypicFeature'
ROOT_ENTITY = 'biolink:NamedThing'
SEQUENCE_VARIANT = 'biolink:SequenceVariant'

# valid trait types for RAGs studies
RAGS_TRAIT_TYPES = [
    CHEMICAL_SUBSTANCE,
    DISEASE,
    PHENOTYPIC_FEATURE
]

# constants for RAGs study types
GWAS = 'GWAS'
MWAS = 'MWAS'

# valid study types for RAGs
RAGS_STUDY_TYPES = [
    GWAS,
    MWAS
]

# constants for errors
RAGS_ERROR_SEARCHING = 40001
RAGS_ERROR_BUILDING = 40002
RAGS_ERROR_NORMALIZATION = 40003


@dataclass
class RAGsAssociation:
    p_value: float
    beta: float


@dataclass
class RAGsNode:
    id: str
    type: str
    name: str = None
    properties: dict = field(default_factory=dict)
    all_types: frozenset = field(default_factory=frozenset)
    synonyms: set = field(default_factory=set)

    def get_synonyms_by_prefix(self, prefix: str):
        return set(filter(lambda x: Text.get_curie(x).upper() == prefix.upper(), self.synonyms))

    def __hash__(self):
        return hash(self.id)


@dataclass
class RAGsEdge:
    id: str
    subject_id: str
    object_id: str
    original_object_id: str
    predicate: str
    relation: str
    provided_by: str
    namespace: str = None
    project_id: str = None
    project_name: str = None
    properties: dict = field(default_factory=dict)

    def __key(self):
        return self.subject_id, self.object_id, self.original_object_id, self.predicate, self.namespace

    def __hash__(self):
        return hash(self.__key())


@dataclass
class SignificantHit:
    id: int
    original_id: str
    original_name: str = None
    normalized: bool = False
    normalized_id: str = None
    normalized_name: str = None
    written: bool = False

@dataclass
class GWASHit(SignificantHit):
    hgvs: str = None
    chrom: str = None
    pos: int = None
    ref: str = None
    alt: str = None


@dataclass
class MWASHit(SignificantHit):
    pass


class AllHitsContainer(object):

    def __init__(self):
        # a dictionary of containers holding the significant hits for each study type (gwas, mwas..)
        self.all_containers = {}
        # initialize the proper hit bucket for each type if it isn't provided
        for study_type in RAGS_STUDY_TYPES:
            if study_type not in self.all_containers:
                self.all_containers[study_type] = hits_container_factory(study_type)

    def get_hits_container_by_type(self, study_type: str):
        return self.all_containers[study_type]

    def add_hit_by_type(self, study_type: str, hit: SignificantHit):
        self.all_containers[study_type].add_hit(hit)


def bucket_default_dict():
    return defaultdict(list)


@staticmethod
def hits_container_factory(study_type):
    if study_type == GWAS:
        return SequenceVariantContainer()
    elif study_type == MWAS:
        return MetaboliteContainer()


class SignificantHitsContainer(object):
    def get_hit_count(self):
        counter = 0
        for hit in self.iterate():
            counter += 1
        return counter

    def add_hit(self, hit: SignificantHit):
        raise NotImplementedError

    def iterate(self):
        raise NotImplementedError


class SequenceVariantContainer(SignificantHitsContainer):
    def __init__(self):
        self.variant_dict = defaultdict(bucket_default_dict)

    def add_hit(self, new_variant: GWASHit):
        self.variant_dict[new_variant.chrom][new_variant.pos].append(new_variant)

    def get_variant(self, chrom: str, pos: int, ref: str, alt: str):
        for var in self.variant_dict[chrom][pos]:
            if var.ref == ref and var.alt == alt:
                return var
        return None

    def iterate(self):
        for chromosome, position_dict in self.variant_dict.items():
            for position, variants in position_dict.items():
                for variant in variants:
                    yield variant

    def to_string(self, verbose=False):
        logger_string = ''
        verbose_logger_string = ''
        variant_count = 0
        for chromosome, position_dict in self.variant_dict.items():
            chromosome_variant_count = 0
            for position, variants in position_dict.items():
                for variant in variants:
                    variant_count += 1
                    chromosome_variant_count += 1
                    if verbose:
                        verbose_logger_string += f'{variant}\n'

            logger_string += f'chromosome {chromosome} had {chromosome_variant_count} variants.\n'
        logger_string += f'Variant Dictionary ({variant_count}) total variants'
        if verbose:
            logger_string += f'\n{verbose_logger_string}'
        return logger_string


class MetaboliteContainer(SignificantHitsContainer):
    def __init__(self):
        self.metabolites = {}

    def add_hit(self, new_metabolite: MWASHit):
        self.metabolites[new_metabolite.original_id] = new_metabolite

    def iterate(self):
        for k, v in self.metabolites.items():
            yield v
