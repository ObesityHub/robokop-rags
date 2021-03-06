from fastapi import Depends, FastAPI, HTTPException, Form, UploadFile, File
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
import os
import csv
import pandas as pd

from app_database import SessionLocal, engine

import rags_src.rags_db_models as rags_db_models
import rags_src.node_types as node_types
from rags_src.rags_core import available_rag_types
from rags_src.rags_project import RagsProject
from rags_src.rags_project_db import RagsProjectDB
from rags_src.rags_graph_db import RagsGraphDB

# this actually creates the DB if it doesn't exist
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
    return templates.TemplateResponse("home.html.jinja", {"request": request})


@app.get("/projects/")
def view_projects(request: Request, db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request,
                        "projects": get_projects_for_display(db)}
    return templates.TemplateResponse("projects.html.jinja", template_context)


@app.post("/add_project/")
def add_project(request: Request,
                new_project_name: str = Form(...),
                rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    if rags_project_db.project_exists_by_name(new_project_name):
        template_context["error_message"] = f'A project with that name already exists. ({new_project_name})'
    else:
        if rags_project_db.create_project(new_project_name):
            template_context["success_message"] = f'A new project was added. ({new_project_name})'
        else:
            template_context["error_message"] = f'Error adding project. Possibly already exists. ({new_project_name})'

    template_context["projects"] = get_projects_for_display(rags_project_db)

    return templates.TemplateResponse("projects.html.jinja", template_context)


@app.post("/delete_project/")
def delete_project(request: Request,
                   project_id: int = Form(...),
                   rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    rags_graph_db = RagsGraphDB()
    rags_graph_db.delete_project(project_id)
    if rags_project_db.project_exists_by_id(project_id):
        rags_project_db.delete_project(project_id)
    else:
        raise HTTPException(status_code=400, detail="That project doesn't exist or was already deleted.")

    template_context["success_message"] = f'Project deleted successfully.'
    template_context["projects"] = get_projects_for_display(rags_project_db)

    return templates.TemplateResponse("projects.html.jinja", template_context)


def get_projects_for_display(rags_project_db: RagsProjectDB):
    projects = rags_project_db.get_projects()
    for project in projects:
        project.num_searched = 0
        project.num_written = 0
        project.num_validated = 0
        for r in project.rags:
            if r.searched:
                project.num_searched += 1
            if r.written:
                project.num_written += 1
            if r.validated:
                project.num_validated += 1
        project.num_rags = len(project.rags)
    return projects


@app.get("/project/{project_id}")
def edit_project(project_id: int,
                 request: Request,
                 rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    if not rags_project_db.project_exists_by_id(project_id):
        template_context["error_message"] = f"Oh No. That project seems to be missing from the database."
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_edit_project_view_template(rags_project_db, project_id, template_context)


@app.post("/project/add_rags/{project_id}")
def add_rags_by_file(request: Request,
                     project_id: int,
                     uploaded_rags_file: UploadFile = File(...),
                     rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    if not rags_project_db.project_exists_by_id(project_id):
        template_context["error_message"] = f"Oh No. That project seems to be missing from the database."
        return templates.TemplateResponse("error.html.jinja", template_context)

    try:
        dataframe = pd.read_csv(uploaded_rags_file.file, header=0)
        error_message = ""
        for i, row in dataframe.iterrows():
            new_rag_name = row["rag_name"]
            if rags_project_db.rag_exists(project_id, new_rag_name):
                error_message += f'A RAG with the name ({new_rag_name}) already exists in this project.\n'
            new_rag_type = row["rag_type"]
            as_node_curie = row["associated_node_id"]
            as_node_type = row["associated_node_type"]
            as_node_label = row["associated_node_label"]
            p_value_cutoff = float(row["p_value_cutoff"])
            file_path = row["file_path"]
            max_p_value = float(row["max_p_value"]) if "max_p_value" in row else None
            has_tabix = False
            if "has_tabix" in row:
                if row["has_tabix"] is True:
                    has_tabix = True

            real_file_path = f'{os.environ["RAGS_DATA_DIR"]}/{file_path}'
            if not rags_project_db.create_rag(project_id=project_id,
                                              rag_name=new_rag_name,
                                              rag_type=new_rag_type,
                                              as_node_type=as_node_type,
                                              as_node_curie=as_node_curie,
                                              as_node_label=as_node_label,
                                              p_value_cutoff=p_value_cutoff,
                                              max_p_value=max_p_value,
                                              file_path=real_file_path,
                                              has_tabix=has_tabix):
                error_message += f'Error creating {new_rag_name}.\n'
        if error_message:
            template_context["error_message"] = "Errors:\n" + error_message

        return get_edit_project_view_template(rags_project_db, project_id, template_context)

    except (KeyError, TypeError, ValueError) as e:
        template_context["error_message"] = f"Oh No. Error parsing the rags project file: {e}"
        return templates.TemplateResponse("error.html.jinja", template_context)


@app.post("/project/add_rag/{project_id}")
def add_rag(request: Request,
            project_id: int,
            new_rag_name: str = Form(...),
            new_rag_type: str = Form(...),
            as_node_type: str = Form(...),
            as_node_curie: str = Form(...),
            as_node_label: str = Form(...),
            p_value_cutoff: float = Form(...),
            max_p_value: float = Form(...),
            file_path: str = Form(...),
            has_tabix: bool = Form(False),
            rags_project_db: RagsProjectDB = Depends(get_db)):

    template_context = {"request": request}
    if not rags_project_db.project_exists_by_id(project_id):
        template_context["error_message"] = f"Oh No. That project seems to be missing from the database."
        return templates.TemplateResponse("error.html.jinja", template_context)

    if rags_project_db.rag_exists(project_id, new_rag_name):
        template_context["error_message"] = f'A RAG with that name ({new_rag_name}) already exists in this project.'
        return get_edit_project_view_template(rags_project_db, project_id, template_context)
    else:
        real_file_path = f'{os.environ["RAGS_DATA_DIR"]}/{file_path}'
        if rags_project_db.create_rag(project_id=project_id,
                                   rag_name=new_rag_name,
                                   rag_type=new_rag_type,
                                   as_node_type=as_node_type,
                                   as_node_curie=as_node_curie,
                                   as_node_label=as_node_label,
                                   p_value_cutoff=p_value_cutoff,
                                   max_p_value=max_p_value,
                                   file_path=real_file_path,
                                   has_tabix=has_tabix):
            template_context["success_message"] = f'A new association study was added. ({new_rag_name})'
        else:
            template_context["error_message"] = f'Error creating ({new_rag_name}).'

        return get_edit_project_view_template(rags_project_db, project_id, template_context)


@app.post("/delete_rag/")
def delete_rag(request: Request,
               rag_id: int = Form(...),
               rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    rag = rags_project_db.get_rag_by_id(rag_id)
    if rag:
        if rags_project_db.delete_rag(rag):
            template_context["success_message"] = f'Rag deleted successfully.'
        else:
            template_context["error_message"] = f"That rag doesn't exist or was already deleted."
    else:
        raise HTTPException(status_code=400, detail="That rag doesn't exist or was already deleted.")

    return get_edit_project_view_template(rags_project_db, rag.project_id, template_context)


@app.post("/search/{project_id}")
def prep_rags(request: Request,
              project_id: int,
              rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    db_project = rags_project_db.get_project_by_id(project_id)
    rags_project = RagsProject(db_project, rags_project_db)
    results = rags_project.prep_rags()
    if "error_message" in results:
        template_context["error_message"] = results["error_message"]
    elif "success_message" in results:
        template_context["success_message"] = results["success_message"]

    return get_edit_project_view_template(rags_project_db, project_id, template_context)


@app.post("/build/{project_id}")
def build_rags(request: Request,
               project_id: int,
               rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    db_project = rags_project_db.get_project_by_id(project_id)
    rags_project = RagsProject(db_project, rags_project_db)
    rags_project.prep_rags()
    results = rags_project.build_rags()
    if "error_message" in results:
        template_context["error_message"] = results["error_message"]
    elif "success_message" in results:
        template_context["success_message"] = results["success_message"]

    return get_edit_project_view_template(rags_project_db, project_id, template_context)


def get_edit_project_view_template(rags_project_db: RagsProjectDB, project_id: int, template_context: dict):
    project = rags_project_db.get_project_by_id(project_id)
    template_context["project"] = project
    template_context["rags"] = project.rags
    template_context["rag_type_list"] = available_rag_types
    template_context["node_type_list"] = node_types.available_node_types
    return templates.TemplateResponse("edit_project.html.jinja", template_context)


@app.get("/project_query/{project_id}")
def project_query_view(project_id: int, request: Request, rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    if not rags_project_db.project_exists_by_id(project_id):
        template_context["error_message"] = f"Oh No. That project seems to be missing from the database."
        return templates.TemplateResponse("error.html.jinja", template_context)

    return get_project_query_view(rags_project_db, project_id, template_context)


@app.get("/project_query/{project_id}/{query_id}")
def project_query_view(project_id: int, query_id:int, request: Request, rags_project_db: RagsProjectDB = Depends(get_db)):
    template_context = {"request": request}
    if not rags_project_db.project_exists_by_id(project_id):
        template_context["error_message"] = f"Oh No. That project seems to be missing from the database."
        return templates.TemplateResponse("error.html.jinja", template_context)

    rags_graph_db = RagsGraphDB()
    if query_id == 1:
        custom_query = f"match (s:{node_types.SEQUENCE_VARIANT})<-[r:related_to{{project_id: {project_id}}}]-(b) return distinct s.id, r.namespace, b.id, r.p_value ORDER BY r.p_value"
        results = rags_graph_db.query_the_graph(custom_query, limit=50)
        template_context["project_query"] = custom_query + " (limited to 50 results)"
        template_context["project_query_results"] = results
        template_context["project_query_headers"] = ["Variant", "Association Study", "Associated with", "p-value"]
    elif query_id == 2:
        custom_query = f"match (c:{node_types.CHEMICAL_SUBSTANCE})<-[r:related_to{{project_id: {project_id}}}]-(b) return distinct c.id, r.namespace, b.id, r.p_value ORDER BY r.p_value"
        results = rags_graph_db.query_the_graph(custom_query, limit=50)
        template_context["project_query"] = custom_query + " (limited to 50 results)"
        template_context["project_query_results"] = results
        template_context["project_query_headers"] = ["Metabolite", "Association Study", "Associated with", "p-value"]
    elif query_id == 3:
        custom_query = f"MATCH (s:{node_types.SEQUENCE_VARIANT})<-[r1:related_to{{project_id: {project_id}}}]-(d:{node_types.DISEASE_OR_PHENOTYPIC_FEATURE})-[r2:related_to{{project_id: {project_id}}}]-(c:{node_types.CHEMICAL_SUBSTANCE})-[r3:related_to{{project_id: {project_id}}}]-(s) return s.id, r1.p_value, d.id, r2.p_value, c.id, r3.p_value ORDER BY r1.p_value"
        results = rags_graph_db.query_the_graph(custom_query, limit=50)
        template_context["project_query"] = custom_query + " (limited to 50 results)"
        template_context["project_query_results"] = results
        template_context["project_query_headers"] = ["Variant", "Var-Pheno p-value", "Phenotype", "Pheno-Chemical p-value", "Chemical", "Chemical-Var p-value"]
    elif query_id == 4:
        custom_query = f"MATCH (c:chemical_substance)--(g:gene)--(v:sequence_variant)-[x{{project_id: {project_id}}}]-(d:disease_or_phenotypic_feature)-[y]-(c) WHERE x.p_value < 1e-5 AND y.p_value < 1e-6 RETURN d.id, c.id, y.p_value, v.id, x.p_value, g.id"


    return get_project_query_view(rags_project_db, project_id, template_context)


def get_project_query_view(rags_project_db: RagsProjectDB, project_id: int, template_context: dict):
    project = rags_project_db.get_project_by_id(project_id)
    template_context["project"] = project

    return templates.TemplateResponse("project_queries.html.jinja", template_context)


