'''Factory function that builds the attribute-URI-to-handler dispatch map.

The router (``router.py``) needs to know which handler method to call for each
RDMO attribute URI that arrives in a signal. This module assembles that map once
at startup by resolving question URIs from the RDMO database and pairing them
with the appropriate ``Information`` handler methods from each sub-package.

Provides:

- ``build_post_save_handler_set``   — post-save dispatch dict (all catalogs)
- ``build_post_delete_handler_set`` — post-delete dispatch dict (all catalogs)
- ``build_presave_validator_map``   — pre-save validation dispatch dict
  (model + algorithm + workflow + publication)
'''

from .constants import (
    BASE_URI,
    CATALOG_MODEL_NAME,
    CATALOG_MODEL_BASICS_NAME,
    CATALOG_ALGORITHM_NAME,
    CATALOG_WORKFLOW_NAME,
)
from .getters import get_questions
from .model.handlers import Information as ModelInformation
from .algorithm.handlers import Information as AlgorithmInformation
from .workflow.handlers import Information as WorkflowInformation
from .publication.handlers import Information as PublicationInformation
from .handlers import Information as GeneralInformation
from .validators import (
    validate_archive_year,
    validate_doi,
    validate_value_format,
    validate_properties,
    validate_qudt_id,
    validate_reference,
    validate_short_description,
    validate_single_line,
)

def build_post_save_handler_set():
    """Build and return the post-save attribute-URI-to-handler dispatch set.

    Loads question URI configurations from the RDMO database for all four
    catalogs (model, algorithm, workflow, publication), instantiates the
    corresponding ``Information`` handler objects, and maps each relevant
    attribute URI to the correct handler method.

    Returns:
        dict: Nested mapping of the form
        ``{catalog_slug: {absolute_attribute_uri: handler_method}}``.
        Each inner dict is passed to the router so that incoming
        ``value_created`` / ``value_updated`` signals can be dispatched
        without any per-signal lookups.
    """

    base = BASE_URI
    handler_map = {}

    # Questions
    questions_model = get_questions('model')
    questions_algorithm = get_questions('algorithm')
    questions_workflow = get_questions('workflow')
    questions_publication = get_questions('publication')

    # Information Classes
    model = ModelInformation()
    algorithm = AlgorithmInformation()
    workflow = WorkflowInformation()
    publication = PublicationInformation()
    general = GeneralInformation()

    # Model handlers
    handler_map.update({
        CATALOG_MODEL_NAME: {
            f"{base}{questions_model['Research Field']['ID']['uri']}":
                model.field,
            f"{base}{questions_model['Research Problem']['ID']['uri']}":
                model.problem,
            f"{base}{questions_model['Quantity']['ID']['uri']}":
                model.quantity,
            f"{base}{questions_model['Mathematical Formulation']['ID']['uri']}":
                model.formulation,
            f"{base}{questions_model['Task']['ID']['uri']}":
                model.task,
            f"{base}{questions_model['Mathematical Model']['ID']['uri']}":
                model.model,
            f'{base}{questions_model["Task"]["QRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Task"]["MFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Formulation"]["Element Quantity"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Quantity"]["Element Quantity"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["MFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["Assumption"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Task"]["Assumption"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Formulation"]["Assumption"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Formulation"]["MFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Research Problem"]["RFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["RPRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["TRelatant"]["uri"]}':
                general.relation,
            f"{base}{questions_publication['Publication']['ID']['uri']}":
                publication.citation,
        }
    })

    # Model handlers
    handler_map.update({
        CATALOG_MODEL_BASICS_NAME: {
            f"{base}{questions_model['Research Problem']['ID']['uri']}":
                model.problem,
            f"{base}{questions_model['Task']['ID']['uri']}":
                model.task,
            f"{base}{questions_model['Mathematical Model']['ID']['uri']}":
                model.model,
            f"{base}{questions_model['Mathematical Formulation']['ID']['uri']}":
                model.formulation,
            f'{base}{questions_model["Mathematical Model"]["RPRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["TRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["MFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Model"]["Assumption"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Task"]["MFRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Task"]["Assumption"]["uri"]}':
                general.relation,
            f'{base}{questions_model["Mathematical Formulation"]["Assumption"]["uri"]}':
                general.relation,
            f"{base}{questions_publication['Publication']['ID']['uri']}":
                publication.citation,
        }
    })

    # Algorithm handlers
    handler_map.update({
        CATALOG_ALGORITHM_NAME: {
            f"{base}{questions_algorithm['Benchmark']['ID']['uri']}":
                algorithm.benchmark,
            f"{base}{questions_algorithm['Software']['ID']['uri']}":
                algorithm.software,
            f"{base}{questions_algorithm['Problem']['ID']['uri']}":
                algorithm.problem,
            f"{base}{questions_algorithm['Algorithm']['ID']['uri']}":
                algorithm.algorithm,
            f'{base}{questions_algorithm["Problem"]["BRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_algorithm["Software"]["BRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_algorithm["Algorithm"]["PRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_algorithm["Algorithm"]["SRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_algorithm["Software"]["Dependency"]["uri"]}':
                general.relation,
            f"{base}{questions_publication['Publication']['ID']['uri']}":
                publication.citation,
        }
    })

    # Workflow handlers
    handler_map.update({
        CATALOG_WORKFLOW_NAME: {
            f"{base}{questions_workflow['Workflow']['ID']['uri']}":
                workflow.workflow,
            f"{base}{questions_workflow['Algorithm']['ID']['uri']}":
                workflow.algorithm,
            f"{base}{questions_workflow['Workflow']['Model']['uri']}":
                workflow.model,
            f"{base}{questions_workflow['Software']['ID']['uri']}":
                workflow.software,
            f"{base}{questions_workflow['Hardware']['ID']['uri']}":
                workflow.hardware,
            f"{base}{questions_workflow['Hardware']['CPU']['uri']}":
                workflow.processor_cores,
            f"{base}{questions_workflow['Data Set']['ID']['uri']}":
                workflow.data_set,
            f"{base}{questions_workflow['Process Step']['ID']['uri']}":
                workflow.process_step,
            f'{base}{questions_workflow["Process Step"]["Algorithm"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Process Step"]["Hardware"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Process Step"]["Input"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Process Step"]["Output"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Workflow"]["PSRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Process Step"]["Software"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Algorithm"]["SRelatant"]["uri"]}':
                general.relation,
            f'{base}{questions_workflow["Software"]["Dependency"]["uri"]}':
                general.relation,
            f"{base}{questions_publication['Publication']['ID']['uri']}":
                publication.citation,
        }
    })

    return handler_map


def build_post_delete_handler_set():
    """Build and return the post-delete attribute-URI-to-handler dispatch set.

    Covers:

    - Publication catalog: when a Publication value set is deleted, the dependent
      citation values are cleaned up via
      :meth:`~MaRDMO.publication.handlers.Information.publication_delete`.

    Returns:
        dict: Nested mapping of the form
        ``{catalog_slug: {absolute_attribute_uri: handler_method}}``,
        structured identically to the map returned by
        :func:`build_post_save_handler_set`.
    """

    base = BASE_URI
    questions_publication = get_questions('publication')
    publication = PublicationInformation()

    pub_set_uri = f"{base}{questions_publication['Publication']['uri']}"

    return {
        CATALOG_MODEL_NAME: {
            pub_set_uri: publication.publication_delete,
        },
        CATALOG_MODEL_BASICS_NAME: {
            pub_set_uri: publication.publication_delete,
        },
        CATALOG_ALGORITHM_NAME: {
            pub_set_uri: publication.publication_delete,
        },
        CATALOG_WORKFLOW_NAME: {
            pub_set_uri: publication.publication_delete,
        },
    }


def build_presave_validator_map():
    """Build and return the pre-save attribute-URI-to-validator dispatch map.

    Maps each attribute URI that requires pre-save validation to the appropriate
    validator function from :mod:`MaRDMO.validators`.  Registered validators:

    - :func:`~MaRDMO.validators.validate_short_description` — for all entity
      ``Description`` question URIs across all catalogs (max
      :data:`~MaRDMO.validators.SHORT_DESCRIPTION_MAX_LENGTH` characters).
    - :func:`~MaRDMO.validators.validate_properties` — for the four data-property
      question URIs (model, formulation, quantity, task) in the model catalogs.
    - :func:`~MaRDMO.validators.validate_qudt_id` — for the Quantity reference
      URI in the full model catalog only.
    - :func:`~MaRDMO.validators.validate_doi` — for the publication reference
      URIs in all catalogs and the data-set "to publish" DOI in the workflow
      catalog.
    - :func:`~MaRDMO.validators.validate_reference` — DOI, URL and swMATH ID
      check for the software/benchmark references and the process-step
      documentation.
    - :func:`~MaRDMO.validators.validate_archive_year` — for the data-set
      "to archive" year in the workflow catalog.
    - :func:`~MaRDMO.validators.validate_value_format` — for all
      ``general.relation`` question URIs across model, algorithm, and workflow.
    - :func:`~MaRDMO.validators.validate_single_line` — for all textarea
      answers exported as text statements (long descriptions, formula
      reference, workflow procedure, reproducibility comments).

    Returns:
        dict: Nested mapping of the form
        ``{catalog_slug: {absolute_attribute_uri: validator_fn}}``.
    """
    base = BASE_URI
    questions_model       = get_questions('model')
    questions_algorithm   = get_questions('algorithm')
    questions_workflow    = get_questions('workflow')
    questions_publication = get_questions('publication')

    return {
        CATALOG_MODEL_NAME: {
            # Short description (all 6 entity types)
            f'{base}{questions_model["Research Field"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Research Problem"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Quantity"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Mathematical Formulation"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Task"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Mathematical Model"]["Description"]["uri"]}':
                validate_short_description,
            # Single-line textarea answers
            f'{base}{questions_model["Research Field"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Research Problem"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Quantity"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Mathematical Formulation"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Task"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Mathematical Model"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_model["Mathematical Formulation"]["Reference"]["uri"]}':
                validate_single_line,
            # Data properties (model, formulation, quantity, task)
            f'{base}{questions_model["Mathematical Model"]["Properties"]["uri"]}':
                validate_properties,
            f'{base}{questions_model["Mathematical Formulation"]["Properties"]["uri"]}':
                validate_properties,
            f'{base}{questions_model["Quantity"]["Properties"]["uri"]}':
                validate_properties,
            f'{base}{questions_model["Task"]["Properties"]["uri"]}':
                validate_properties,
            # QUDT reference ID (quantity only)
            f'{base}{questions_model["Quantity"]["Reference"]["uri"]}':
                validate_qudt_id,
            # DOI reference (publication)
            f'{base}{questions_publication["Publication"]["Reference"]["uri"]}':
                validate_doi,
            # Relation label format
            f'{base}{questions_model["Task"]["QRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Task"]["MFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Formulation"]["Element Quantity"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Quantity"]["Element Quantity"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["MFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["Assumption"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Task"]["Assumption"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Formulation"]["Assumption"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Formulation"]["MFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Research Problem"]["RFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["RPRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["TRelatant"]["uri"]}':
                validate_value_format,
        },
        CATALOG_MODEL_BASICS_NAME: {
            # Short description (Research Problem, Formulation, Task, Model only)
            f'{base}{questions_model["Research Problem"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Mathematical Formulation"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Task"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_model["Mathematical Model"]["Description"]["uri"]}':
                validate_short_description,
            # Single-line textarea answers (no long descriptions in basics catalog)
            f'{base}{questions_model["Mathematical Formulation"]["Reference"]["uri"]}':
                validate_single_line,
            # Data properties (no Quantity in basics catalog)
            f'{base}{questions_model["Mathematical Model"]["Properties"]["uri"]}':
                validate_properties,
            f'{base}{questions_model["Mathematical Formulation"]["Properties"]["uri"]}':
                validate_properties,
            f'{base}{questions_model["Task"]["Properties"]["uri"]}':
                validate_properties,
            # DOI reference (publication)
            f'{base}{questions_publication["Publication"]["Reference"]["uri"]}':
                validate_doi,
            # Relation label format
            f'{base}{questions_model["Mathematical Model"]["RPRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["TRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["MFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Model"]["Assumption"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Task"]["MFRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Task"]["Assumption"]["uri"]}':
                validate_value_format,
            f'{base}{questions_model["Mathematical Formulation"]["Assumption"]["uri"]}':
                validate_value_format,
        },
        CATALOG_ALGORITHM_NAME: {
            # Short description
            f'{base}{questions_algorithm["Algorithm"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_algorithm["Problem"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_algorithm["Software"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_algorithm["Benchmark"]["Description"]["uri"]}':
                validate_short_description,
            # DOI reference (publication); DOI, URL or swMATH ID (software, benchmark)
            f'{base}{questions_publication["Publication"]["Reference"]["uri"]}':
                validate_doi,
            f'{base}{questions_algorithm["Software"]["Reference"]["uri"]}':
                validate_reference,
            f'{base}{questions_algorithm["Benchmark"]["Reference"]["uri"]}':
                validate_reference,
            # Relation label format
            f'{base}{questions_algorithm["Problem"]["BRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_algorithm["Software"]["BRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_algorithm["Algorithm"]["PRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_algorithm["Algorithm"]["SRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_algorithm["Software"]["Dependency"]["uri"]}':
                validate_value_format,
        },
        CATALOG_WORKFLOW_NAME: {
            # Short description
            f'{base}{questions_workflow["Workflow"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_workflow["Algorithm"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_workflow["Software"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_workflow["Hardware"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_workflow["Data Set"]["Description"]["uri"]}':
                validate_short_description,
            f'{base}{questions_workflow["Process Step"]["Description"]["uri"]}':
                validate_short_description,
            # Single-line textarea answers (procedure, reproducibility comments)
            f'{base}{questions_workflow["Workflow"]["Long Description"]["uri"]}':
                validate_single_line,
            f'{base}{questions_workflow["Workflow"]["Mathematical"]["uri"]}':
                validate_single_line,
            f'{base}{questions_workflow["Workflow"]["Runtime"]["uri"]}':
                validate_single_line,
            f'{base}{questions_workflow["Workflow"]["Result"]["uri"]}':
                validate_single_line,
            f'{base}{questions_workflow["Workflow"]["Original Platform"]["uri"]}':
                validate_single_line,
            f'{base}{questions_workflow["Workflow"]["Other Platform"]["uri"]}':
                validate_single_line,
            # DOI reference (publication, DS to-publish); DOI, URL or swMATH ID (software, PS documentation)
            f'{base}{questions_publication["Publication"]["Reference"]["uri"]}':
                validate_doi,
            f'{base}{questions_workflow["Software"]["Reference"]["uri"]}':
                validate_reference,
            f'{base}{questions_workflow["Process Step"]["Software-Documentation"]["uri"]}':
                validate_reference,
            f'{base}{questions_workflow["Process Step"]["Method-Documentation"]["uri"]}':
                validate_reference,
            f'{base}{questions_workflow["Data Set"]["To Publish"]["uri"]}':
                validate_doi,
            f'{base}{questions_workflow["Data Set"]["To Archive"]["uri"]}':
                validate_archive_year,
            # Relation label format
            f'{base}{questions_workflow["Process Step"]["Algorithm"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Process Step"]["Hardware"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Process Step"]["Input"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Process Step"]["Output"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Workflow"]["PSRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Process Step"]["Software"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Algorithm"]["SRelatant"]["uri"]}':
                validate_value_format,
            f'{base}{questions_workflow["Software"]["Dependency"]["uri"]}':
                validate_value_format,
        },
    }
