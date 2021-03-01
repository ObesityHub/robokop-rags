import os
import logging

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from rags_src.util import LoggingUtil


logger = LoggingUtil.init_logging("rags.rags_graph_db", logging.INFO,
                                  format='medium',
                                  logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsGraphDBConnectionError(Exception):
    def __init__(self, error_message: str):
        self.message = error_message


class RagsGraphDB(object):
    """
    This is just a wrapper for the graph db driver.

    For now that means the official Neo4j driver.
    """
    def __init__(self):
        try:
            self.graph_db_driver = GraphDatabase.driver(f"bolt://{os.environ['NEO4J_HOST']}:{os.environ['NEO4J_BOLT_PORT']}",
                                                        auth=("neo4j", os.environ['NEO4J_PASSWORD']))
        except ServiceUnavailable as e:
            raise RagsGraphDBConnectionError(e)
        except ValueError as e:
            raise RagsGraphDBConnectionError(e)

    """
    Retrieve a session from the driver, this should be used as a context manager.
    
    graph_db = RagsGraphDB()
    with graph_db.get_session() as session:
        session.write_transaction()
        ...
    """
    def get_session(self):
        return self.graph_db_driver.session()

    def custom_read_query(self, query: str, limit: int = None) -> list:

        if limit is not None:
            query += f' limit {limit}'
        logger.debug(f'graph db query: {query}')
        try:
            with self.get_session() as session:
                results = session.read_transaction(run_query, query)
                logger.debug(f'graph db response: {results}')
        except ServiceUnavailable as e:
            raise RagsGraphDBConnectionError(e)
        except ValueError as e:
            raise RagsGraphDBConnectionError(e)

        return results

    def custom_write_query(self, query: str) -> bool:

        logger.debug(f'graph db query: {query}')
        try:
            with self.get_session() as session:
                results = session.write_transaction(run_query, query)
                logger.debug(f'graph db response: {results}')
        except ServiceUnavailable as e:
            raise RagsGraphDBConnectionError(e)
        except ValueError as e:
            raise RagsGraphDBConnectionError(e)

        return True

    def delete_project(self, project_id: int):
        with self.get_session() as session:
            session.run(f'match (a)-[r{{project_id:{project_id}}}]-(b) delete r')

    def __del__(self):
        if self.graph_db_driver:
            self.graph_db_driver.close()


def run_query(tx, query):
    results = tx.run(query)
    return list(results)


