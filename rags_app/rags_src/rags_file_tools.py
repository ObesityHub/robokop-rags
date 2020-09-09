from rags_src.rags_core import SignificantHit, GWASHit, MWASHit, SequenceVariantContainer, MetaboliteContainer, SimpleAssociation
from rags_src.util import LoggingUtil

from dataclasses import dataclass
import logging
import csv
import tabix
import gzip
import os
import sys

logger = LoggingUtil.init_logging("rags.rags_file_tools", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


@dataclass
class GWASFile:
    file_path: str
    has_tabix: bool = True
    delimiter: str = '\t'
    reference_genome: str = 'HG19'
    reference_patch: str = 'p1'


@dataclass
class MWASFile:
    file_path: str
    delimiter: str = ','


class MWASFileReader:
    def __init__(self, mwas_file: MWASFile):
        self.mwas_file = mwas_file
        #self.file_handler = open(self.mwas_file.file_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        #if self.file_handler:
        #    self.file_handler.close()
        pass

    def find_significant_hits(self, p_value_cutoff: float):
        # TODO - improve this - it should support TSV and other header variations
        hit_container, num_found = MetaboliteContainer(), 0
        try:
            with open(self.mwas_file.file_path) as f:
                csv_reader = csv.reader(f)
                headers = next(csv_reader)
                line_counter = 0
                curie_index = None
                name_index = None
                pval_index = None
                for header in headers:
                    if header == 'curie':
                        curie_index = headers.index(header)
                    if header == 'label':
                        name_index = headers.index(header)
                    elif ('pval' in header.lower()) or ('pvalue' in header.lower()):
                        pval_index = headers.index(header)
                    elif 'beta' in header.lower():
                        beta_index = headers.index(header)

                if curie_index is None or name_index is None or pval_index is None:
                    logger.warning(f'Error reading file headers for {self.mwas_file.file_path} - {headers}')
                    return False, hit_container, None

                for data in csv_reader:
                    try:
                        line_counter += 1
                        p_value_string = data[pval_index]
                        p_value = float(p_value_string)
                        if p_value <= p_value_cutoff:
                            new_hit = MWASHit(id=None, original_curie=data[curie_index], original_label=data[name_index])
                            hit_container.add_hit(new_hit)
                            num_found += 1
                    except IndexError as e:
                        logger.warning(f'Error parsing file {self.mwas_file.file_path}, on line {line_counter}: {e}')
                    except ValueError as e:
                        logger.warning(f'Error converting {p_value_string} to float in {self.mwas_file.file_path}')
                logger.info(f'Found {num_found} significant metabolites in {self.mwas_file.file_path}!')
        except IOError:
            logger.warning(f'Could not open file: {self.mwas_file.file_path}')
            return False, hit_container, None

        return True, hit_container, num_found

    def get_mwas_association_from_file(self, mwas_hit: MWASHit):
        association_line = None
        try:
            with open(self.mwas_file.file_path) as f:
                csv_reader = csv.reader(f)
                headers = next(csv_reader)
                line_counter = 0
                curie_index = None
                name_index = None
                pval_index = None
                for header in headers:
                    if header == 'curie':
                        curie_index = headers.index(header)
                    if header == 'label':
                        name_index = headers.index(header)
                    elif ('pval' in header.lower()) or ('pvalue' in header.lower()):
                        pval_index = headers.index(header)
                    elif 'beta' in header.lower():
                        beta_index = headers.index(header)

                if curie_index is None or name_index is None or pval_index is None:
                    logger.warning(f'Error reading file headers for {self.mwas_file.file_path} - {headers}')
                    return False

                for data in csv_reader:
                    try:
                        line_counter += 1
                        if data[curie_index] == mwas_hit.original_curie:
                            association_line = data
                            break
                    except IndexError as e:
                        logger.warning(f'Error parsing file {self.mwas_file.file_path}, on line {line_counter}: {e}')
                    except ValueError as e:
                        logger.warning(f'Error converting {p_value_string} to float in {self.mwas_file.file_path}')
        except IOError:
            logger.warning(f'Could not open file: {self.mwas_file.file_path}')

        if association_line:
            try:
                p_value = float(association_line[pval_index])
                # a value less than the minimum float representation will end up as 0 here
                if p_value == 0:
                    # we set it to the minimum value instead
                    p_value = sys.float_info.min
                beta = float(association_line[beta_index])
                return SimpleAssociation(p_value, beta)
            except ValueError as e:
                logger.warning(f'Error: Bad p value or beta in file {self.gwas_file.file_path}: {e}')
        else:
            return None


class GWASFileReader:

    reference_chrom_labels = {
        'HG19': {
            'p1': {
                '1': 'NC_000001.10',
                '2': 'NC_000002.11',
                '3': 'NC_000003.11',
                '4': 'NC_000004.11',
                '5': 'NC_000005.9',
                '6': 'NC_000006.11',
                '7': 'NC_000007.13',
                '8': 'NC_000008.10',
                '9': 'NC_000009.11',
                '10': 'NC_000010.10',
                '11': 'NC_000011.9',
                '12': 'NC_000012.11',
                '13': 'NC_000013.10',
                '14': 'NC_000014.8',
                '15': 'NC_000015.9',
                '16': 'NC_000016.9',
                '17': 'NC_000017.10',
                '18': 'NC_000018.9',
                '19': 'NC_000019.9',
                '20': 'NC_000020.10',
                '21': 'NC_000021.8',
                '22': 'NC_000022.10',
                '23': 'NC_000023.10',
                '24': 'NC_000024.9',
                'X': 'NC_000023.10',
                'Y': 'NC_000024.9'
            }
        },
        'HG38': {
            'p1': {
                '1': 'NC_000001.11',
                '2': 'NC_000002.12',
                '3': 'NC_000003.12',
                '4': 'NC_000004.12',
                '5': 'NC_000005.10',
                '6': 'NC_000006.12',
                '7': 'NC_000007.14',
                '8': 'NC_000008.11',
                '9': 'NC_000009.12',
                '10': 'NC_000010.11',
                '11': 'NC_000011.10',
                '12': 'NC_000012.12',
                '13': 'NC_000013.11',
                '14': 'NC_000014.9',
                '15': 'NC_000015.10',
                '16': 'NC_000016.10',
                '17': 'NC_000017.11',
                '18': 'NC_000018.10',
                '19': 'NC_000019.10',
                '20': 'NC_000020.11',
                '21': 'NC_000021.9',
                '22': 'NC_000022.11',
                '23': 'NC_000023.11',
                '24': 'NC_000024.10',
                'X': 'NC_000023.11',
                'Y': 'NC_000024.10'
            }
        }
    }

    def __init__(self, gwas_file: GWASFile, use_tabix: bool = False):
        self.possible_chrom_labels = ['chrom', 'chr', 'chromosome']
        self.possible_pos_labels = ['pos', 'position']
        self.possible_ref_labels = ['ref']
        self.possible_alt_labels = ['alt']
        self.possible_p_value_labels = ['pvalue', 'pval', 'p_value', 'p_val']
        self.possible_beta_labels = ['beta']
        self.gwas_file = gwas_file
        self.use_tabix = use_tabix
        self.file_handler = None
        self.initialized = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.file_handler:
            self.file_handler.close()

        if exc_type == tabix.TabixError:
            logger.error(f'TabixError: {exc_value} could not open tabix file {self.gwas_file.file_path} ')
            # raise IOError('Could not open tabix file') ?
            return True
        elif exc_type == IOError:
            logger.error(f'IOError: {exc_value} could not open file {self.gwas_file.file_path} ')
            return True
        elif exc_type == FileNotFoundError:
            logger.error(f'FileNotFoundError: {exc_value} could not open file {self.gwas_file.file_path} ')
            return True
        elif exc_type == IndexError:
            logger.error(f'IndexError: {exc_value} index error in file {self.gwas_file.file_path} - {exc_value}')
            return True

    def initialize_reader(self):
        if not self.initialized:
            self.file_handler = self.create_normal_file_handler()
            header_list = next(self.file_handler).split()
            headers = [header.lower() for header in header_list]
            for chrom_label in self.possible_chrom_labels:
                if chrom_label in headers:
                    self.chrom_index = headers.index(chrom_label)
                    break
            for pos_label in self.possible_pos_labels:
                if pos_label in headers:
                    self.pos_index = headers.index(pos_label)
                    break
            for ref_label in self.possible_ref_labels:
                if ref_label in headers:
                    self.ref_index = headers.index(ref_label)
                    break
            for alt_label in self.possible_alt_labels:
                if alt_label in headers:
                    self.alt_index = headers.index(alt_label)
                    break
            for p_val_label in self.possible_p_value_labels:
                if p_val_label in headers:
                    self.p_val_index = headers.index(p_val_label)
                    break
            for beta_label in self.possible_beta_labels:
                if beta_label in headers:
                    self.beta_index = headers.index(beta_label)
                    break

            if (not hasattr(self, 'chrom_index') or
                    not hasattr(self, 'pos_index') or
                    not hasattr(self, 'ref_index') or
                    not hasattr(self, 'alt_index') or
                    not hasattr(self, 'p_val_index') or
                    not hasattr(self, 'beta_index')):
                logger.error(f'Error: Bad file headers in {self.gwas_file.file_path} - {headers}')
                raise IndexError(f'Bad file headers in {self.gwas_file.file_path} - {headers}')

            if self.use_tabix:
                self.file_handler.close()
                self.tabix_file_handler = tabix.open(f'{self.gwas_file.file_path}')
            else:
                # seek back to the beginning then skip the headers
                self.file_handler.seek(0)
                next(self.file_handler)

            self.initialized = True

    def create_normal_file_handler(self):
        if self.gwas_file.file_path.endswith('.gz'):
            return gzip.open(self.gwas_file.file_path, mode='rt')
        else:
            return open(self.gwas_file.file_path)

    def find_significant_hits(self,
                              p_value_cutoff: float):
        try:
            self.initialize_reader()
        except OSError as e:
            logger.error(f'Error reading file {self.gwas_file.file_path}: {e}')
            return False, None, None

        variant_container = SequenceVariantContainer()
        sig_variants_found = 0
        sig_variants_failed_conversion = 0
        line_counter = 0
        for line in self.file_handler:
            try:
                line_counter += 1
                data = line.split()
                #print(f'checking line {data}')
                p_value_string = data[self.p_val_index]
                p_value = float(p_value_string)
                if p_value <= p_value_cutoff:
                    # we're assuming 23 and 24 instead of X and Y here, might not always be the case
                    chromosome = data[self.chrom_index]
                    position = int(data[self.pos_index])
                    ref_allele = data[self.ref_index]
                    alt_allele = data[self.alt_index]

                    hgvs = self.convert_vcf_to_hgvs(self.gwas_file.reference_genome,
                                                    self.gwas_file.reference_patch,
                                                    chromosome,
                                                    position,
                                                    ref_allele,
                                                    alt_allele)
                    if hgvs:
                        new_variant = GWASHit(id=None,
                                              hgvs=hgvs,
                                              chrom=chromosome,
                                              pos=position,
                                              ref=ref_allele,
                                              alt=alt_allele)
                        variant_container.add_hit(new_variant)
                        sig_variants_found += 1
                    else:
                        sig_variants_failed_conversion += 1

            except (IndexError, ValueError) as e:
                logger.error(f'Error reading file {self.gwas_file.file_path}, on line {line_counter}: {e}')

        gwas_filename = self.gwas_file.file_path.rsplit('/', 1)[-1]
        logger.info(f'Finding variants in {gwas_filename} complete. {line_counter} lines searched.')
        logger.info(f'In {gwas_filename} {sig_variants_found} significant variants found and converted.')
        if sig_variants_failed_conversion > 0:
            logger.error(f'In {gwas_filename} {sig_variants_failed_conversion} other significant variants failed to convert to hgvs.')
        return True, variant_container, sig_variants_found

    def convert_vcf_to_hgvs(self, reference_genome, reference_patch, chromosome, position, ref_allele, alt_allele):
        try:
            ref_chromosome = self.reference_chrom_labels[reference_genome][reference_patch][chromosome]
        except KeyError:
            logger.warning(f'Reference chromosome and/or version not found: {reference_genome}.{reference_patch},{chromosome}')
            return ''
        
        # assume vcf has integers and not X or Y for now
        # if chromosome == 'X':
        #    chromosome = '23'
        # elif chromosome == 'Y':
        #    chromosome = '24'

        len_ref = len(ref_allele)
        if alt_allele == '.':
            # deletions
            if len_ref == 1:
                variation = f'{position}del'
            else:
                variation = f'{position}_{position+len_ref-1}del'

        elif alt_allele.startswith('<'):
            # we know about these but don't support them yet
            return ''

        else:
            len_alt = len(alt_allele)
            if (len_ref == 1) and (len_alt == 1):
                # substitutions
                variation = f'{position}{ref_allele}>{alt_allele}'
            elif (len_alt > len_ref) and alt_allele.startswith(ref_allele):
                # insertions
                diff = len_alt - len_ref
                offset = len_alt - diff 
                variation = f'{position+offset-1}_{position+offset}ins{alt_allele[offset:]}'
            elif (len_ref > len_alt) and ref_allele.startswith(alt_allele):
                # deletions
                diff = len_ref - len_alt
                offset = len_ref - diff
                if diff == 1:
                    variation = f'{position+offset}del'
                else:
                    variation = f'{position+offset}_{position+offset+diff-1}del'
            else:
                logger.warning(f'Format of variant not recognized for hgvs conversion: {ref_allele} to {alt_allele}')
                return ''
        
        hgvs = f'{ref_chromosome}:g.{variation}'
        return hgvs

    def get_gwas_association_from_file(self, sequence_variant: SignificantHit):
        self.initialize_reader()
        if self.use_tabix:
            association_line = self.__get_gwas_association_from_indexed_file(sequence_variant)
        else:
            association_line = self.__get_gwas_assocation_from_text_file(sequence_variant)
        
        if association_line:
            try:
                p_value = float(association_line[self.p_val_index])
                # a value less than the minimum float representation will end up as 0 here
                if p_value == 0:
                    # we set it to the minimum value instead
                    p_value = sys.float_info.min
                beta = float(association_line[self.beta_index])
                return SimpleAssociation(p_value, beta)
            except ValueError as e:
                logger.warning(f'Error: Bad p value or beta in file {self.gwas_file.file_path}: {e}')
        else:
            return None

    def __get_gwas_association_from_indexed_file(self, sequence_variant: GWASHit):
        # "not sure why tabix needs position -1" - according to PyVCF Docs
        # seems to be true for now
        position_end = sequence_variant.pos
        position_start = sequence_variant.pos - 1
        chromosome = sequence_variant.chrom
        #
        try:
            records = self.tabix_file_handler.query(chromosome, position_start, position_end)
            for line in records:
                if (sequence_variant.alt == line[self.alt_index]) \
                        and (sequence_variant.ref == line[self.ref_index]):
                    return line
        except tabix.TabixError:
            logger.error(f'Error: TabixError ({self.gwas_file.file_path}) chromosome({sequence_variant.chrom}) positions({position_start}-{position_end})')

        return None

    def __get_gwas_assocation_from_text_file(self, sequence_variant: GWASHit):
        try:
            self.file_handler.seek(1)
            csv_reader = csv.reader(self.file_handler, delimiter=self.gwas_file.delimiter, skipinitialspace=True)
            for data in csv_reader:
                if ((data[self.chrom_index] == sequence_variant.chrom)
                        and (int(data[self.pos_index]) == sequence_variant.pos)
                        and (data[self.alt_index] == sequence_variant.alt)
                        and (data[self.ref_index] == sequence_variant.ref)):
                    return data
        except (csv.Error, TypeError) as e:
            logger.error(f'CSVReader error in ({self.gwas_file.file_path}): {e}')
        return None

