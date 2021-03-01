import pytest
import os

import rags_src.rags_project_db_models as rags_db_models
from rags_src.rags_core import GWAS, MWAS, DISEASE, CHEMICAL_SUBSTANCE, ROOT_ENTITY

from rags_src.rags_project import RagsProjectManager
from rags_src.rags_project_db import RagsProjectDB

from app_database import TestSessionLocal, test_database_engine, TEST_DATABASE_LOCATION

if os.path.exists(TEST_DATABASE_LOCATION):
    os.remove(TEST_DATABASE_LOCATION)

rags_db_models.Base.metadata.create_all(bind=test_database_engine)

SAMPLE_DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'sample_data',
    )

@pytest.fixture()
def testing_db():
    try:
        db = TestSessionLocal()
        yield RagsProjectDB(db)
    finally:
        db.close()


def reset_db(testing_db):
    testing_db.db.execute(f'DELETE FROM {rags_db_models.RAGS_PROJECTS_TABLE_NAME}')
    testing_db.db.execute(f'DELETE FROM  {rags_db_models.RAGS_STUDY_TABLE_NAME}')
    testing_db.db.execute(f'DELETE FROM  {rags_db_models.GWAS_HITS_TABLE_NAME}')
    testing_db.db.execute(f'DELETE FROM  {rags_db_models.MWAS_HITS_TABLE_NAME}')
    testing_db.db.commit()


def test_project_creation(testing_db: RagsProjectDB):
    reset_db(testing_db)
    assert testing_db.get_project_by_name('Testing Project') is None
    testing_db.create_project('Testing Project')
    new_project_id = testing_db.get_project_by_name('Testing Project').id
    assert testing_db.project_exists_by_id(new_project_id)


def test_project_deletion(testing_db: RagsProjectDB):
    reset_db(testing_db)
    testing_db.create_project('Testing Project')
    new_project_id = testing_db.get_project_by_name('Testing Project').id
    testing_db.delete_project(new_project_id)
    assert testing_db.project_exists_by_id(new_project_id) is False
    assert testing_db.get_project_by_name('Testing Project') is None


def test_get_projects(testing_db: RagsProjectDB):
    reset_db(testing_db)
    testing_db.create_project('Testing Project')
    testing_db.create_project('Testing Project 2')
    testing_db.create_project('Testing Project 3')
    projects = testing_db.get_projects()
    assert len(projects) == 3

    for p in projects:
        assert type(p) == rags_db_models.RAGsProject
        assert 'Test' in p.name


def create_project_with_rags(testing_db: RagsProjectDB):
    testing_db.create_project('Testing Project')
    project_id = testing_db.get_project_by_name('Testing Project').id
    testing_db.create_study(project_id=project_id,
                            file_path=f'sample_sugen.gz',
                            study_name="Testing GWAS 1",
                            study_type=GWAS,
                            original_trait_id='MONDO:0011122',
                            original_trait_type=DISEASE,
                            original_trait_label='Obesity',
                            p_value_cutoff=0.005,
                            max_p_value=1,
                            has_tabix=True)
    testing_db.create_study(project_id=project_id,
                            file_path=f'sample_sugen2.gz',
                            study_name="Testing GWAS 2",
                            study_type=GWAS,
                            original_trait_id='MONDO:0011122',
                            original_trait_type=DISEASE,
                            original_trait_label='Obesity',
                            p_value_cutoff=0.005,
                            max_p_value=1,
                            has_tabix=True)
    testing_db.create_study(project_id=project_id,
                            file_path=f'sample_sugen3.gz',
                            study_name="Testing GWAS 3",
                            study_type=GWAS,
                            original_trait_id='MONDO:0011122',
                            original_trait_type=DISEASE,
                            original_trait_label='Obesity',
                            p_value_cutoff=0.005,
                            max_p_value=1,
                            has_tabix=True)
    testing_db.create_study(project_id=project_id,
                            file_path=f'sample_sugen4.gz',
                            study_name="Testing GWAS 4",
                            study_type=GWAS,
                            original_trait_id='MONDO:0011122',
                            original_trait_type=DISEASE,
                            original_trait_label='Obesity',
                            p_value_cutoff=0.005,
                            max_p_value=1,
                            has_tabix=True)
    testing_db.create_study(project_id=project_id,
                            file_path=f'sample_mwas',
                            study_name="Testing MWAS",
                            study_type=MWAS,
                            original_trait_id='MONDO:0011122',
                            original_trait_type=DISEASE,
                            original_trait_label='Obesity',
                            p_value_cutoff=0.005,
                            max_p_value=1)
    return project_id


def test_create_rags(testing_db: RagsProjectDB):
    reset_db(testing_db)
    project_id = create_project_with_rags(testing_db)
    assert len(testing_db.get_all_studies(project_id)) == 5
    assert testing_db.study_exists(project_id, 'Testing GWAS 1')
    assert testing_db.study_exists(project_id, 'Testing GWAS 2')
    assert testing_db.study_exists(project_id, 'Testing GWAS 3')
    assert testing_db.study_exists(project_id, 'Testing GWAS 4')

    r = testing_db.get_study_by_name('Testing GWAS 1')
    assert r.study_type == GWAS
    assert r.file_path == f'sample_sugen.gz'
    assert r.p_value_cutoff == 0.005
    assert r.original_trait_id == 'MONDO:0011122'
    assert r.original_trait_type == DISEASE
    assert r.original_trait_label == 'Obesity'
    assert not r.searched
    assert not r.written


def test_process_rag_traits(testing_db: RagsProjectDB):
    reset_db(testing_db)
    project_id = create_project_with_rags(testing_db)
    db_project = testing_db.get_project_by_id(project_id)
    test_project = RagsProjectManager(db_project.id, db_project.name, testing_db)
    test_project.process_traits()

    for study in testing_db.get_all_studies(project_id):
        assert study.trait_normalized


def test_search_rags(testing_db: RagsProjectDB):
    reset_db(testing_db)
    project_id = create_project_with_rags(testing_db)
    db_project = testing_db.get_project_by_id(project_id)
    test_project = RagsProjectManager(db_project.id, db_project.name, testing_db)
    test_project.search_studies()

    for r in testing_db.get_all_studies(project_id):
        assert r.searched
        if r.study_name == 'Testing GWAS 1':
            assert r.num_hits == 0
        elif r.study_name == 'Testing GWAS 2':
            assert r.num_hits == 1
        elif r.study_name == 'Testing GWAS 3':
            assert r.num_hits == 7

    hits = testing_db.get_all_gwas_hits(project_id)
    assert len(hits) == 8
    for h in hits:
        assert not h.written


def test_delete_rags(testing_db: RagsProjectDB):
    reset_db(testing_db)
    project_id = create_project_with_rags(testing_db)
    for study in testing_db.get_all_studies(project_id):
        testing_db.delete_study(study)
    assert len(testing_db.get_all_studies(project_id)) == 0


# actually writes to the graph, but there is no test graph neo4j, so this is not active by default
# TODO use a flag or something to test graph building and validation without interfering with existing projects
def a_test_build_rags(testing_db: RagsProjectDB):

    reset_db(testing_db)
    project_id = create_project_with_rags(testing_db)
    db_project = testing_db.get_project_by_id(project_id)
    test_project = RagsProjectManager(db_project.id, db_project.name, testing_db)

    result = test_project.process_traits()
    assert result.success
    result = test_project.search_studies()
    assert result.success
    result = test_project.build_rags()
    assert result.success

    rags = testing_db.get_all_studies(project_id)
    for r in rags:
        assert r.searched
        assert r.written

    hits = testing_db.get_unprocessed_gwas_hits(project_id)
    assert len(hits) == 0
