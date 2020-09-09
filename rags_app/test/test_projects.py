import pytest
import os

import rags_src.rags_db_models as rags_db_models
import rags_src.rags_core as rags_core
import rags_src.node_types as node_types

from rags_src.rags_project import RagsProject
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
def project_db():
    try:
        db = TestSessionLocal()
        yield RagsProjectDB(db)
    finally:
        db.close()


def reset_db(project_db):
    project_db.db.execute(f'DELETE FROM {rags_db_models.PROJECTS_TABLE_NAME}')
    project_db.db.execute(f'DELETE FROM  {rags_db_models.RAGS_TABLE_NAME}')
    project_db.db.execute(f'DELETE FROM  {rags_db_models.GWAS_HITS_TABLE_NAME}')
    project_db.db.execute(f'DELETE FROM  {rags_db_models.MWAS_HITS_TABLE_NAME}')
    project_db.db.commit()


def test_project_creation(project_db: RagsProjectDB):
    reset_db(project_db)
    assert project_db.get_project_by_name('Testing Project') is None
    project_db.create_project('Testing Project')
    new_project_id = project_db.get_project_by_name('Testing Project').id
    assert project_db.project_exists_by_id(new_project_id)


def test_project_deletion(project_db: RagsProjectDB):
    reset_db(project_db)
    project_db.create_project('Testing Project')
    new_project_id = project_db.get_project_by_name('Testing Project').id
    project_db.delete_project(new_project_id)
    assert project_db.project_exists_by_id(new_project_id) is False
    assert project_db.get_project_by_name('Testing Project') is None


def test_get_projects(project_db: RagsProjectDB):
    reset_db(project_db)
    project_db.create_project('Testing Project')
    project_db.create_project('Testing Project 2')
    project_db.create_project('Testing Project 3')
    projects = project_db.get_projects()
    assert len(projects) == 3

    for p in projects:
        assert type(p) == rags_db_models.Project
        assert 'Test' in p.name


def create_project_with_rags(project_db: RagsProjectDB):
    project_db.create_project('Testing Project')
    project_id = project_db.get_project_by_name('Testing Project').id
    project_db.create_rag(project_id=project_id,
                          rag_name="Testing GWAS 1",
                          rag_type=rags_core.GWAS,
                          trait_type=node_types.DISEASE_OR_PHENOTYPIC_FEATURE,
                          trait_curie='MONDO:0011122',
                          trait_label='Obesity',
                          p_value_cutoff=0.005,
                          max_p_value=1,
                          file_path=f'sample_sugen.gz',
                          has_tabix=True)
    project_db.create_rag(project_id=project_id,
                          rag_name="Testing GWAS 2",
                          rag_type=rags_core.GWAS,
                          trait_type=node_types.DISEASE_OR_PHENOTYPIC_FEATURE,
                          trait_curie='MONDO:0011122',
                          trait_label='Obesity',
                          p_value_cutoff=0.005,
                          max_p_value=1,
                          file_path=f'sample_sugen2.gz',
                          has_tabix=True)
    project_db.create_rag(project_id=project_id,
                          rag_name="Testing GWAS 3",
                          rag_type=rags_core.GWAS,
                          trait_type=node_types.DISEASE_OR_PHENOTYPIC_FEATURE,
                          trait_curie='MONDO:0011122',
                          trait_label='Obesity',
                          p_value_cutoff=0.005,
                          max_p_value=1,
                          file_path=f'sample_sugen3.gz',
                          has_tabix=True)
    project_db.create_rag(project_id=project_id,
                          rag_name="Testing GWAS 4",
                          rag_type=rags_core.GWAS,
                          trait_type=node_types.DISEASE_OR_PHENOTYPIC_FEATURE,
                          trait_curie='MONDO:0011122',
                          trait_label='Obesity',
                          p_value_cutoff=0.005,
                          max_p_value=1,
                          file_path=f'sample_sugen4.gz',
                          has_tabix=True)
    project_db.create_rag(project_id=project_id,
                          rag_name="Testing MWAS",
                          rag_type=rags_core.MWAS,
                          trait_type=node_types.DISEASE_OR_PHENOTYPIC_FEATURE,
                          trait_curie='MONDO:0011122',
                          trait_label='Obesity',
                          p_value_cutoff=0.005,
                          max_p_value=1,
                          file_path=f'sample_mwas')
    return project_id


def test_create_rags(project_db: RagsProjectDB):
    reset_db(project_db)
    project_id = create_project_with_rags(project_db)
    assert len(project_db.get_rags(project_id)) == 5
    assert project_db.rag_exists(project_id, 'Testing GWAS 1')
    assert project_db.rag_exists(project_id, 'Testing GWAS 2')
    assert project_db.rag_exists(project_id, 'Testing GWAS 3')
    assert project_db.rag_exists(project_id, 'Testing GWAS 4')

    r = project_db.get_rag_by_name('Testing GWAS 1')
    assert r.rag_type == rags_core.GWAS
    assert r.file_path == f'sample_sugen.gz'
    assert r.p_value_cutoff == 0.005
    assert r.trait_curie == 'MONDO:0011122'
    assert r.trait_type == node_types.DISEASE_OR_PHENOTYPIC_FEATURE
    assert r.trait_label == 'Obesity'
    assert r.searched is False
    assert r.written is False
    assert r.validated is False


def test_delete_rags(project_db: RagsProjectDB):
    reset_db(project_db)
    project_id = create_project_with_rags(project_db)
    for rag in project_db.get_rags(project_id):
        project_db.delete_rag(rag)
    assert len(project_db.get_rags(project_id)) == 0


def test_prep_rags(project_db: RagsProjectDB):
    reset_db(project_db)
    project_id = create_project_with_rags(project_db)
    db_project = project_db.get_project_by_id(project_id)
    test_project = RagsProject(db_project, project_db)
    test_project.prep_rags()

    for r in project_db.get_rags(project_id):
        assert r.searched
        if r.rag_name == 'Testing GWAS 1':
            assert r.num_hits == 0
        elif r.rag_name == 'Testing GWAS 2':
            assert r.num_hits == 1
        elif r.rag_name == 'Testing GWAS 3':
            assert r.num_hits == 7

    hits = project_db.get_all_gwas_hits(project_id)
    assert len(hits) == 8
    for h in hits:
        assert not h.written


def test_build_rags(project_db: RagsProjectDB):
    reset_db(project_db)
    project_id = create_project_with_rags(project_db)
    db_project = project_db.get_project_by_id(project_id)
    test_project = RagsProject(db_project, project_db)
    test_project.prep_rags()
    result = test_project.build_rags()
    assert result['success'] is True

    rags = project_db.get_rags(project_id)
    for r in rags:
        assert r.searched
        assert r.written
        hits = project_db.get_unprocessed_gwas_hits(project_id)
        assert len(hits) == 0
