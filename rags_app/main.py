from fastapi import Depends, FastAPI, HTTPException, Form, UploadFile, File
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import pandas as pd

from app_database import SessionLocal, engine

import rags_src.rags_project_db_models as rags_db_models
from rags_src.rags_core import RAGS_TRAIT_TYPES, RAGS_STUDY_TYPES, GWAS, MWAS, SEQUENCE_VARIANT, DISEASE_OR_PHENOTYPIC_FEATURE, CHEMICAL_SUBSTANCE
from rags_src.rags_project import RagsProjectManager, RagsProjectResults
from rags_src.rags_project_db import RagsProjectDB
from rags_src.rags_graph_db import RagsGraphDB, RagsGraphDBConnectionError
from rags_src.rags_normalizer import RagsNormalizationError

# create the DB tables if needed
rags_db_models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory=f'{os.environ["RAGS_HOME"]}/rags_app/static'), name="static")

templates = Jinja2Templates(directory=f'{os.environ["RAGS_HOME"]}/rags_app/templates')


# DB dependency
def get_db():
    try:
        db = SessionLocal()
        yield RagsProjectDB(db)
    finally:
        db.close()


@app.get("/")
def landing_page(request: Request):
    template_context = {"request": request}
    return templates.TemplateResponse("home.html.jinja", template_context)


@app.get("/projects/")
def view_projects(request: Request,
                  rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    set_up_projects_for_display(template_context, rags_project_db)
    return templates.TemplateResponse("projects.html.jinja", template_context)


@app.post("/add_project/")
def add_project(request: Request,
                new_project_name: str = Form(...),
                rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if rags_project_db.project_exists_by_name(new_project_name):
        show_error_message(template_context, f'A project with that name already exists. ({new_project_name})')
    else:
        if rags_project_db.create_project(new_project_name):
            show_success_message(template_context, f'A new project was added. ({new_project_name})')
        else:
            show_error_message(template_context, f'Error adding project. ({new_project_name})')

    set_up_projects_for_display(template_context, rags_project_db)
    return templates.TemplateResponse("projects.html.jinja", template_context)


@app.post("/delete_project/")
def delete_project(request: Request,
                   project_id: int = Form(...),
                   rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        error_message = "That project doesn't exist or was already deleted."
        show_error_message(template_context, error_message)
        return templates.TemplateResponse("error.html.jinja", template_context)

    try:
        rags_graph_db = RagsGraphDB()
        rags_graph_db.delete_project(project_id)
    except RagsGraphDBConnectionError:
        show_graph_db_connection_error(template_context)
        return templates.TemplateResponse("error.html.jinja", template_context)

    rags_project_db.delete_project(project_id)
    show_success_message(template_context, f'Project deleted successfully.')

    set_up_projects_for_display(template_context, rags_project_db)
    return templates.TemplateResponse("projects.html.jinja", template_context)


def set_up_projects_for_display(template_context: dict, rags_project_db: RagsProjectDB):
    # here we are dynamically adding some properties jinja expects to the project objects
    # this is pretty inefficient, these could be stored in the DB
    template_context["projects"] = rags_project_db.get_projects()
    for project in template_context["projects"]:
        project.num_gwas_files = 0
        project.num_gwas_hits = 0
        project.num_mwas_files = 0
        project.num_mwas_hits = 0
        project.num_errors = 0
        for study in project.studies:
            if study.study_type == GWAS:
                project.num_gwas_files += 1
                if study.num_hits:
                    project.num_gwas_hits += study.num_hits
            elif study.study_type == MWAS:
                project.num_mwas_files += 1
                if study.num_hits:
                    project.num_mwas_hits += study.num_hits
            project.num_errors += len(study.errors)


@app.get("/project/{project_id}")
def manage_project(project_id: int,
                   request: Request,
                   rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        return get_missing_project_view_template(template_context)

    return get_manage_project_view_template(rags_project_db, project_id, template_context)


@app.post("/add_studies/")
def add_studies_by_file(request: Request,
                        project_id: int = Form(...),
                        uploaded_studies_file: UploadFile = File(...),
                        rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        return get_missing_project_view_template(template_context)

    success = True
    try:
        dataframe = pd.read_csv(uploaded_studies_file.file, header=0)
        for i, row in dataframe.iterrows():
            study_name = row["study_name"]
            if rags_project_db.study_exists(project_id, study_name):
                show_warning_message(template_context,
                                     f'An association study with the name ({study_name}) already exists.')
            else:
                study_type = row["study_type"]
                original_trait_id = row["trait_id"]
                original_trait_type = row["trait_type"]
                original_trait_label = row["trait_label"]
                p_value_cutoff = float(row["p_value_threshold"])
                max_p_value = float(row["max_p_value"]) if "max_p_value" in row else None
                file_path = row["file_path"]
                has_tabix = True if "has_tabix" in row and row["has_tabix"] else False

                if not rags_project_db.create_study(project_id=project_id,
                                                    file_path=file_path,
                                                    study_name=study_name,
                                                    study_type=study_type,
                                                    original_trait_id=original_trait_id,
                                                    original_trait_type=original_trait_type,
                                                    original_trait_label=original_trait_label,
                                                    p_value_cutoff=p_value_cutoff,
                                                    max_p_value=max_p_value,
                                                    has_tabix=has_tabix):
                    show_error_message(template_context, f'Error creating {study_name}.')
                    success = False

    except KeyError as k:
        error_message = f"Error parsing the association studies file. (KeyError: Key not found {k})"
        show_error_message(template_context, error_message)
        return templates.TemplateResponse("error.html.jinja", template_context)
    except (TypeError, ValueError) as e:
        error_message = f"TypeError or ValueError parsing the association studies file. (Error: {e})"
        show_error_message(template_context, error_message)
        return templates.TemplateResponse("error.html.jinja", template_context)

    if success:
        show_success_message(template_context, "Association studies were added to the project successfully.")
        show_warning_message(template_context, 'Continue to "Build Graph" when you are done adding studies!')

    return get_manage_project_view_template(rags_project_db, project_id, template_context)


@app.post("/add_study/")
def add_study(request: Request,
              project_id: int = Form(...),
              study_name: str = Form(...),
              study_type: str = Form(...),
              trait_id: str = Form(...),
              trait_type: str = Form(...),
              trait_label: str = Form(...),
              p_value_threshold: float = Form(...),
              max_p_value: float = Form(...),
              file_path: str = Form(...),
              has_tabix: bool = Form(False),
              rags_project_db: RagsProjectDB = Depends(get_db)):

    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        return get_missing_project_view_template(template_context)

    if rags_project_db.study_exists(project_id, study_name):
        show_warning_message(template_context,
                             f'An association study with that name ({study_name}) already exists in this project.')
        return get_manage_project_view_template(rags_project_db, project_id, template_context)

    if rags_project_db.create_study(project_id=project_id,
                                    study_name=study_name,
                                    study_type=study_type,
                                    original_trait_id=trait_id,
                                    original_trait_type=trait_type,
                                    original_trait_label=trait_label,
                                    p_value_cutoff=p_value_threshold,
                                    max_p_value=max_p_value,
                                    file_path=file_path,
                                    has_tabix=has_tabix):
        show_success_message(template_context, f'A new association study was added. ({study_name})')
        show_warning_message(template_context, 'Continue to "Build Graph" when you are done adding studies!')
    else:
        show_error_message(template_context, f'Error creating ({study_name}).')

    return get_manage_project_view_template(rags_project_db, project_id, template_context)


@app.post("/delete_study/")
def delete_study(request: Request,
                 study_id: int = Form(...),
                 rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    study = rags_project_db.get_study_by_id(study_id)
    if study and rags_project_db.delete_study(study):
        study_name = study.study_name
        show_success_message(template_context, f"Association study {study_name} was deleted successfully.")
    else:
        show_error_message(template_context, "That association study doesn't exist or was already deleted.")

    return get_manage_project_view_template(rags_project_db, study.project_id, template_context)


@app.post("/build/")
def build_rags(request: Request,
               project_id: int = Form(...),
               force_rebuild: bool = Form(...),
               rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    db_project = rags_project_db.get_project_by_id(project_id)
    project_manager = RagsProjectManager(db_project.id, db_project.name, rags_project_db)

    try:
        results = project_manager.process_traits(force_rebuild=force_rebuild)
        update_template_context_with_results(results, template_context)
        if not results.success:
            return templates.TemplateResponse("error.html.jinja", template_context)

        results = project_manager.search_studies()
        update_template_context_with_results(results, template_context)

        results = project_manager.build_rags(force_rebuild=force_rebuild)
        update_template_context_with_results(results, template_context)
        if not results.success:
            return templates.TemplateResponse("error.html.jinja", template_context)

    except RagsGraphDBConnectionError:
        show_graph_db_connection_error(template_context)
        return templates.TemplateResponse("error.html.jinja", template_context)
    except RagsNormalizationError as e:
        show_error_message(template_context, e.message)
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_manage_project_view_template(rags_project_db, project_id, template_context)


@app.post("/annotate/")
def annotate_rags(request: Request,
                  project_id: int = Form(...),
                  rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    db_project = rags_project_db.get_project_by_id(project_id)
    project_manager = RagsProjectManager(db_project.id, db_project.name, rags_project_db)

    try:
        results = project_manager.annotate_hits()
        update_template_context_with_results(results, template_context)
    except RagsGraphDBConnectionError:
        show_graph_db_connection_error(template_context)
        return templates.TemplateResponse("error.html.jinja", template_context)
    except RagsNormalizationError as e:
        show_error_message(template_context, e.message)
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_manage_project_view_template(rags_project_db, project_id, template_context)


def get_missing_project_view_template(template_context: dict):
    template_context["error_message"] = f"Oh No. Project not found."
    return templates.TemplateResponse("error.html.jinja", template_context)


def get_manage_project_view_template(rags_project_db: RagsProjectDB, project_id: int, template_context: dict):
    project = rags_project_db.get_project_by_id(project_id)
    template_context["project"] = project
    template_context["studies"] = project.studies
    template_context["study_type_list"] = RAGS_STUDY_TYPES
    template_context["trait_type_list"] = RAGS_TRAIT_TYPES
    return templates.TemplateResponse("project_management.html.jinja", template_context)


@app.get("/project_query/{project_id}")
def project_query_view(project_id: int, request: Request, rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        show_error_message(template_context, "Oh No. That project seems to be missing from the database.")
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_project_query_view(rags_project_db, project_id, template_context)


@app.get("/project_query/{project_id}/{query_id}")
def project_query_view(project_id: int,
                       query_id: int,
                       request: Request,
                       rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = init_template_context(request)
    if not rags_project_db.project_exists_by_id(project_id):
        show_error_message(template_context, f"Oh No. That project seems to be missing from the database.")
        return templates.TemplateResponse("error.html.jinja", template_context)

    try:
        rags_graph_db = RagsGraphDB()
        normalized_association_predicate = "biolink:correlated_with"
        if query_id == 1:
            custom_query = f"match (s:`{SEQUENCE_VARIANT}`)<-[r:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(b) return distinct s.id, r.input_id, r.namespace, b.id, r.p_value ORDER BY r.p_value"
            results = rags_graph_db.custom_read_query(custom_query, limit=150)
            template_context["project_query"] = custom_query + " (limited to 150 results)"
            template_context["project_query_results"] = results
            template_context["project_query_headers"] = ["Variant ID", "Original ID", "Association Study", "Associated with", "p-value"]
        elif query_id == 2:
            custom_query = f"match (c:`{CHEMICAL_SUBSTANCE}`)<-[r:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(b) return distinct c.id, r.input_id, r.namespace, b.id, r.p_value ORDER BY r.p_value"
            results = rags_graph_db.custom_read_query(custom_query, limit=150)
            template_context["project_query"] = custom_query + " (limited to 150 results)"
            template_context["project_query_results"] = results
            template_context["project_query_headers"] = ["Metabolite ID", "Original ID", "Association Study", "Associated with", "p-value"]
        elif query_id == 3:
            custom_query = f"MATCH (s:`{SEQUENCE_VARIANT}`)<-[r1:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(d:`{DISEASE_OR_PHENOTYPIC_FEATURE}`)-[r2:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(c:`{CHEMICAL_SUBSTANCE}`)-[r3:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(s) return s.id, r1.p_value, d.id, r2.p_value, c.id, r3.p_value ORDER BY r1.p_value"
            results = rags_graph_db.custom_read_query(custom_query, limit=150)
            template_context["project_query"] = custom_query + " (limited to 150 results)"
            template_context["project_query_results"] = results
            template_context["project_query_headers"] = ["Variant", "Var-Pheno p-value", "Phenotype", "Pheno-Chemical p-value", "Chemical", "Chemical-Var p-value"]
        elif query_id == 4:
            custom_query = f"MATCH (s:`{SEQUENCE_VARIANT}`)-[r1:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(d:`{DISEASE_OR_PHENOTYPIC_FEATURE}`)-[r2:`{normalized_association_predicate}` {{project_id: {project_id}}}]-(c:`{CHEMICAL_SUBSTANCE}`)-[r3]-(g:gene)-[r4]-(s) WHERE r1.p_value < 1e-5 AND r2.p_value < 1e-5 RETURN s.id, r1.p_value, d.id, r2.p_value, c.id, type(r3), g.id, type(r4)"
            results = rags_graph_db.custom_read_query(custom_query, limit=150)
            template_context["project_query"] = custom_query + " (limited to 150 results)"
            template_context["project_query_results"] = results
            template_context["project_query_headers"] = ["Variant", "Var-Pheno p-value", "Phenotype", "Pheno-Chemical p-value", "Chemical", "Chem-Gene relationship", "Gene", "Gene-Variant relationship"]
        elif query_id == 5:
            pass
    except RagsGraphDBConnectionError:
        show_graph_db_connection_error(template_context)
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_project_query_view(rags_project_db, project_id, template_context)


def get_project_query_view(rags_project_db: RagsProjectDB, project_id: int, template_context: dict):
    project = rags_project_db.get_project_by_id(project_id)
    template_context["project"] = project

    return templates.TemplateResponse("project_queries.html.jinja", template_context)


def init_template_context(request: Request):
    template_context = {"request": request,
                        "warning_messages": [],
                        "error_messages": []}
    return template_context


def show_warning_message(template_context: dict, message: str):
    template_context["warning_messages"].append(message)


def show_error_message(template_context: dict, message: str):
    template_context["error_messages"].append(message)


def show_graph_db_connection_error(template_context: dict):
    error_message = f"Service Unavailable: Error connecting to the Neo4j database: {e}.\n"
    error_message += "Make sure the neo4j docker container is configured and running properly and try again."
    template_context["error_messages"].append(error_message)


def show_success_message(template_context: dict, message: str):
    template_context["success_message"] = message


def update_template_context_with_results(results: RagsProjectResults, template_context: dict):
    if results.warning_messages:
        template_context["warning_messages"].extend(results.warning_messages)
    if results.error_messages:
        template_context["error_messages"].extend(results.error_messages)
    if results.success:
        template_context["success_message"] = results.success_message
