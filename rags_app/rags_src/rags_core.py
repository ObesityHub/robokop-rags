from collections import defaultdict
from dataclasses import dataclass

GWAS = 'GWAS'
MWAS = 'MWAS'

available_rag_types = [
    GWAS,
    MWAS
]

@dataclass
class Project:
    id: int
    name: str

@dataclass
class RAG:
    id: int
    rag_name: str
    rag_type: str
    trait_type: str
    trait_curie: str
    trait_label: str
    p_value_cutoff: float
    file_path: str
    max_p_value: float = None
    searched: bool = False
    written: bool = False
    validated: bool = False
    num_hits: int = None
    has_tabix: bool = True


@dataclass
class SimpleAssociation:
    p_value: float
    beta: float


@dataclass
class SignificantHit:
    id: int


@dataclass
class GWASHit(SignificantHit):
    hgvs: str
    chrom: str
    pos: int
    ref: str
    alt: str
    curie: str = ''


@dataclass
class MWASHit(SignificantHit):
    original_curie: str
    original_label: str = ''
    curie: str = ''


class AllHitsContainer(object):

    def __init__(self):
        # a dictionary of containers holding the significant hits for each rag type (gwas, mwas..)
        self.all_containers = {}
        # initialize the proper hit bucket for each type if it isn't provided
        for rag_type in available_rag_types:
            if rag_type not in self.all_containers:
                self.all_containers[rag_type] = hits_container_factory(rag_type)

    def get_hits_container_by_type(self, rag_type: str):
        return self.all_containers[rag_type]

    def add_hit_by_type(self, rag_type: str, hit: SignificantHit):
        self.all_containers[rag_type].add_hit(hit)


def bucket_default_dict():
    return defaultdict(list)


@staticmethod
def hits_container_factory(rags_type):
    if rags_type == GWAS:
        return SequenceVariantContainer()
    elif rags_type == MWAS:
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
        self.metabolites[new_metabolite.original_curie] = new_metabolite

    def iterate(self):
        for k, v in self.metabolites.items():
            yield v
