from rags_src.rags_file_tools import GWASFile, GWASFileReader, MWASFile, MWASFileReader
from rags_src.rags_core import GWASHit, MWASHit
import os

SAMPLE_DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'sample_data',
    )


def test_gwas_header_indexing():
    with GWASFileReader(GWASFile('./sample_data/sample_sugen.gz')) as test_file_reader_1:
        test_file_reader_1.initialize_reader(use_tabix=False)
        assert test_file_reader_1.chrom_index == 0
        assert test_file_reader_1.beta_index is not None

    with GWASFileReader(GWASFile('./sample_data/sample_sugen2.gz')) as test_file_reader_1:
        test_file_reader_1.initialize_reader(use_tabix=True)
        assert test_file_reader_1.chrom_index == 0
        assert test_file_reader_1.beta_index is not None


def test_gwas_finding_significant_hits():

    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/sample_sugen.gz', has_tabix=False)) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.05)
        assert results["success"]
        assert results["hit_counter"] == 9

    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/sample_sugen.gz', has_tabix=True)) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.05)
        assert results["success"]
        assert results["hit_counter"] == 9

    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/sample_sugen.gz')) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.005)
        assert results["success"]
        assert results["hit_counter"] == 0

    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/fake_file_name.gz')) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.005)
        assert not results["success"]
        assert results["error_message"]  # make sure there is some error message at least


def test_mwas_finding_significant_hits():
    with MWASFileReader(MWASFile(f'{SAMPLE_DATA_DIR}/sample_mwas')) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.005)
        assert results["success"]
        assert results["hit_counter"] == 5

    with MWASFileReader(MWASFile(f'{SAMPLE_DATA_DIR}/sample_mwas')) as test_file_reader:
        results = test_file_reader.find_significant_hits(0.1)
        assert results["success"]
        assert results["hit_counter"] == 7


def test_get_mwas_association_from_file():
    metabolite = MWASHit(id=None, original_id='PUBCHEM.COMPOUND:11146967')
    metabolite2 = MWASHit(id=None, original_id='HMDB:HMDB0011352')

    with MWASFileReader(MWASFile(f'{SAMPLE_DATA_DIR}/sample_mwas')) as test_file_reader:
        association1 = test_file_reader.get_mwas_association_from_file(metabolite)
        assert association1.p_value == 1.5e-10
        assert association1.beta == 0.0738210759226987

    with MWASFileReader(MWASFile(f'{SAMPLE_DATA_DIR}/sample_mwas')) as test_file_reader:
        association1 = test_file_reader.get_mwas_association_from_file(metabolite2)
        assert association1.p_value == 0.0077
        assert association1.beta == 0.0920163859050238


def test_get_gwas_association_from_file():
    variant = GWASHit(id=None, original_id='NC_000019.9:g.45411941T>C', chrom='19', pos=45411941, ref='T', alt='C')
    variant2 = GWASHit(id=None, original_id='NC_000016.9:g.82335281_82335283del', chrom='16', pos=82335280, ref='AAAC', alt='A')
    variant3 = GWASHit(id=None, original_id='NC_000016.9:g.82335281_82335283del', chrom='16', pos=82335212, ref='AAAC', alt='A')

    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/sample_sugen2.gz', has_tabix=True)) as test_file_reader_1:
        association1 = test_file_reader_1.get_gwas_association_from_file(variant)
        assert association1.p_value == 0.049
        assert association1.beta == 0.005

        association2 = test_file_reader_1.get_gwas_association_from_file(variant2)
        assert association2.p_value == 4.90E-08
        assert association2.beta == 0.005

        # variant 3 is not in the file
        association3 = test_file_reader_1.get_gwas_association_from_file(variant3)
        assert association3 is None

    # this should grab the associations without relying on tabix
    with GWASFileReader(GWASFile(f'{SAMPLE_DATA_DIR}/sample_sugen2.gz', has_tabix=False)) as test_file_reader_2:
        association3 = test_file_reader_2.get_gwas_association_from_file(variant)
        assert association3.p_value == 0.049
        assert association3.beta == 0.005

        association4 = test_file_reader_2.get_gwas_association_from_file(variant2)
        assert association4.p_value == 4.90E-08
        assert association4.beta == 0.005

