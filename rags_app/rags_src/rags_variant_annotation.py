import logging
import subprocess
import time
from subprocess import SubprocessError
from os import path, environ, remove as os_remove
from io import BytesIO
from urllib.request import urlopen
from zipfile import ZipFile
from collections import defaultdict
from rags_src.rags_core import GENE, RAGsNode, RAGsEdge
from rags_src.util import LoggingUtil


logger = LoggingUtil.init_logging("rags.SequenceVariantAnnotator", logging.INFO, format='medium', logFilePath=f'{environ["RAGS_HOME"]}/logs/')


class AnnotationFailedError(Exception):
    def __init__(self, error_message: str, actual_error: str):
        self.error_message = error_message
        self.actual_error = actual_error


class SequenceVariantAnnotator:

    def __init__(self):

        self.workspace_dir = environ["RAGS_HOME"]

        # if the snpEff dir exists, assume we already downloaded it
        self.snpeff_dir = path.join(self.workspace_dir, "snpEff")
        if not path.isdir(self.snpeff_dir):
            # otherwise fetch and unzip SNPEFF
            snpeff_url = 'https://snpeff.blob.core.windows.net/versions/snpEff_latest_core.zip'
            with urlopen(snpeff_url) as snpeff_resource:
                with ZipFile(BytesIO(snpeff_resource.read())) as snpeff_zip:
                    snpeff_zip.extractall(self.workspace_dir)

    def get_variant_annotations(self, variant_nodes: list):

        temp_file_path = path.join(self.workspace_dir, f'temp_{int(time.time())}')

        logger.debug('Creating VCF file from source nodes..')
        temp_vcf_path = f'{temp_file_path}.vcf'
        self.create_vcf_from_variant_nodes(variant_nodes, temp_vcf_path)

        logger.debug('Running SNPEFF, creating annotated VCF..')
        annotated_vcf_path = f'{temp_file_path}_annotated.vcf'
        self.run_snpeff(temp_vcf_path,
                        annotated_vcf_path)

        logger.debug('Converting annotated VCF back to nodes and edges..')
        annotation_results = self.extract_annotations_from_vcf(annotated_vcf_path)

        os_remove(temp_vcf_path)
        os_remove(annotated_vcf_path)

        return annotation_results

    def run_snpeff(self,
                   vcf_file_path: str,
                   annotated_vcf_path: str,
                   ud_distance: int = 500000):

        # changing this reference genome DB may break things,
        # such as assuming gene IDs and biotypes are from ensembl
        reference_genome = 'GRCh38.99'
        try:
            with open(annotated_vcf_path, "w") as new_snpeff_file:
                snpeff_results = subprocess.run(['java', '-Xmx12g', '-jar', 'snpEff.jar', '-noStats', '-ud', str(ud_distance), reference_genome, vcf_file_path],
                                                cwd=self.snpeff_dir,
                                                stdout=new_snpeff_file,
                                                stderr=subprocess.STDOUT)
                snpeff_results.check_returncode()
        except SubprocessError as e:
            logger.error(f'SNPEFF subprocess error - {e}')
            raise AnnotationFailedError('SNPEFF Failed', str(e))

    def extract_annotations_from_vcf(self, annotated_vcf_path: str):

        gene_biotypes_to_ignore = set()
        annotation_results = {'objects': [],
                              'edges': [],
                              'metadata': {}}

        with open(annotated_vcf_path, 'r') as snpeff_output:
            for line in snpeff_output:
                if line.startswith("#") or not line:
                    if 'SnpEffVersion' in line:
                        annotation_results['metadata']['SnpEffVersion'] = line.split("=")[1].strip()
                    if 'SnpEffCmd' in line:
                        annotation_results['metadata']['SnpEffCmd'] = line.split("=")[1].strip()
                    continue
                vcf_line_split = line.split('\t')
                variant_id = vcf_line_split[2]
                info_field = vcf_line_split[7].split(';')
                for info in info_field:
                    if info.startswith('ANN='):
                        annotations_to_write = defaultdict(set)
                        gene_distances = {}
                        annotations = info[4:].split(',')
                        for annotation in annotations:
                            annotation_info = annotation.split('|')
                            effects = annotation_info[1].split("&")
                            genes = annotation_info[4].split('-')
                            gene_biotype = annotation_info[7]
                            distance_info = annotation_info[14]
                            if gene_biotype not in gene_biotypes_to_ignore:
                                for gene in genes:
                                    gene_id = f'ENSEMBL:{gene}'
                                    gene_distances[gene_id] = distance_info
                                    for effect in effects:
                                        if effect == 'intergenic_region':
                                            effect_predicate = 'GAMMA:0000102'
                                        else:
                                            effect_predicate = f'SNPEFF:{effect}'
                                        annotations_to_write[effect_predicate].add(gene_id)
                        for effect_predicate, gene_ids in annotations_to_write.items():
                            for gene_id in gene_ids:
                                if gene_distances[gene_id]:
                                    try:
                                        edge_props = {'distance_to_feature': int(gene_distances[gene_id])}
                                    except ValueError:
                                        edge_props = None
                                else:
                                    edge_props = None

                                annotation_results['objects'].append(RAGsNode(gene_id, GENE, ''))
                                annotation_edge = RAGsEdge(id='',
                                                           subject_id=variant_id,
                                                           object_id=gene_id,
                                                           original_object_id=gene_id,
                                                           predicate=effect_predicate,
                                                           relation=effect_predicate,
                                                           provided_by='infores:snpeff',  # SNPEFF
                                                           properties=edge_props)
                                annotation_results['edges'].append(annotation_edge)
                        break
        return annotation_results

    def create_vcf_from_variant_nodes(self,
                                      source_nodes: list,
                                      vcf_file_path: str):
        with open(vcf_file_path, "w") as vcf_file:
            vcf_file.write('##fileformat=VCFv4.2')
            vcf_headers = "\t".join(["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"])
            vcf_file.write(f'#{vcf_headers}\n')
            for node in source_nodes:
                for curie in node.synonyms:
                    if curie.startswith('ROBO_VAR'):
                        robo_key = curie.split(':', 1)[1]
                        robo_params = robo_key.split('|')
                        chromosome = robo_params[1]
                        position = int(robo_params[2])
                        ref_allele = robo_params[4]
                        alt_allele = robo_params[5]

                        if not ref_allele:
                            ref_allele = f'N'
                            alt_allele = f'N{alt_allele}'
                        elif not alt_allele:
                            ref_allele = f'N{ref_allele}'
                            alt_allele = f'N'
                        else:
                            position += 1

                        current_variant_line = "\t".join([chromosome,
                                                          str(position),
                                                          node.id,
                                                          ref_allele,
                                                          alt_allele,
                                                          '',
                                                          'PASS',
                                                          ''])
                        vcf_file.write(f'{current_variant_line}\n')
                        break
