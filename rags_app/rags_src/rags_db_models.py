from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float
from sqlalchemy.orm import relationship

from app_database import Base

PROJECTS_TABLE_NAME = "projects"
RAGS_TABLE_NAME = "rags"
GWAS_HITS_TABLE_NAME = "gwas_sig_hits"
MWAS_HITS_TABLE_NAME = "mwas_sig_hits"


class Project(Base):
    __tablename__ = PROJECTS_TABLE_NAME

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True)

    rags = relationship("RAG")


class RAG(Base):
    __tablename__ = RAGS_TABLE_NAME

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String)
    rag_name = Column(String)
    rag_type = Column(String)
    as_node_type = Column(String)
    as_node_curie = Column(String)
    as_node_label = Column(String)
    p_value_cutoff = Column(Float)
    max_p_value = Column(Float)
    searched = Column(Boolean)
    written = Column(Boolean)
    validated = Column(Boolean)

    # this could be calculated with relations in the hits tables but lets store it as well for efficiency
    num_hits = Column(Integer)

    # should rag type specific file info be separate? we'll simplify and use one table for now
    has_tabix = Column(Boolean)

    #delimiter: str = '\t'
    #reference_genome: str = 'HG19'
    #reference_patch: str = 'p1'

    project_id = Column(Integer, ForeignKey(f'{PROJECTS_TABLE_NAME}.id'))
    gwas_hits = relationship("GWASHit")
    mwas_hits = relationship("MWASHit")


class GWASHit(Base):
    __tablename__ = GWAS_HITS_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    hgvs = Column(String)
    chrom = Column(String)
    pos = Column(Integer)
    ref = Column(String)
    alt = Column(String)
    curie = Column(String)
    written = Column(Boolean)

    project_id = Column(Integer, ForeignKey(f'{PROJECTS_TABLE_NAME}.id'))
    rag_id = Column(Integer, ForeignKey(f'{RAGS_TABLE_NAME}.id'))


class MWASHit(Base):
    __tablename__ = MWAS_HITS_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    original_curie = Column(String)
    original_label = Column(String)
    curie = Column(String)
    written = Column(Boolean)

    project_id = Column(Integer, ForeignKey(f'{PROJECTS_TABLE_NAME}.id'))
    rag_id = Column(Integer, ForeignKey(f'{RAGS_TABLE_NAME}.id'))