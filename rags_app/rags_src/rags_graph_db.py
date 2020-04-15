from neo4j import GraphDatabase

import os


class RagsGraphDB(object):
    """
    This is just a wrapper for the graph db driver.

    For now that means the official Neo4j driver.
    """
    def __init__(self):
        self.graph_db_driver = GraphDatabase.driver(f"bolt://{os.environ['NEO4J_HOST']}:{os.environ['NEO4J_BOLT_PORT']}",
                                                    auth=("neo4j", os.environ['NEO4J_PASSWORD']))

    """
    Retrieve a session from the driver, this should be used as a context manager.
    
    graph_db = RagsGraphDB()
    with graph_db.get_session() as session:
        session.write_transaction()
        ...
    """
    def get_session(self):
        return self.graph_db_driver.session()

    def query_the_graph(self, query: str, limit: int = None) -> list:

        return_list = []
        with self.get_session() as session:
            if limit is not None:
                query += f' limit {limit}'
            response = session.run(query)

        if response is not None:
            # de-queue the returned data into a list
            return_list = list(response)

        return return_list

    def delete_project(self, project_id: int):
        with self.get_session() as session:
            session.run(f'match (a)-[r:related_to{{project_id={project_id}}}-(b) delete r')

    def __del__(self):
        if self.graph_db_driver:
            self.graph_db_driver.close()




