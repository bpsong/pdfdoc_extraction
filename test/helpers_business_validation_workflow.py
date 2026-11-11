"""Offline synthetic invoice with real versioning, review, resume, and exports."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from modules.base_task import BaseTask
from modules.db.connection import managed_connect
from modules.db.repositories import ExtractionRepository
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.pipeline_definition_service import PipelineDefinitionService
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.workflow_loader import WorkflowLoader
from test.helpers_business_validation import invoice_review_schema
from test.helpers_sqlite import TempConfig


SOURCE_VALUES: dict[str, Any] = {
    'invoice_number': 'RAW-1',
    'items': [{'description': 'Paper', 'quantity': 3, 'unit_price': 10, 'line_total': 300},
              {'description': 'Folders', 'quantity': 2, 'unit_price': 10, 'line_total': 20}],
    'subtotal': 50,
}
ACCEPTED_VALUES: dict[str, Any] = {
    'invoice_number': 'INV-OK',
    'items': [{'description': 'Paper', 'quantity': 3, 'unit_price': 10, 'line_total': 30},
              {'description': 'Folders', 'quantity': 2, 'unit_price': 10, 'line_total': 20}],
    'subtotal': 50,
}
EXPORT_FIELDS: dict[str, Any] = {
    'invoice_number': {'alias': 'Invoice number', 'type': 'str'},
    'subtotal': {'alias': 'Subtotal', 'type': 'float'},
    'items': {'alias': 'Items', 'type': 'List[Any]', 'is_table': True,
              'item_fields': {key: {'alias': key, 'type': 'str' if key == 'description' else 'float'}
                              for key in ('description', 'quantity', 'unit_price', 'line_total')}},
}


def create_invoice_workflow(
    config: TempConfig, directory: Path, *, with_rules: bool = True, extended_rules: bool = False,
    filename_template: str = '{invoice_number}',
) -> dict[str, Any]:
    """Publish and assign a real pipeline with exact schema and output metadata."""
    source = directory / 'synthetic-invoice.pdf'
    source.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
        NameObject('/F1'): DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                           NameObject('/Subtype'): NameObject('/Type1'),
                                           NameObject('/BaseFont'): NameObject('/Helvetica')})})})
    lines = ['SYNTHETIC INVOICE - TEST DATA ONLY', 'Invoice number: INV-OK',
             'Invoice date: 2026-10-01', 'Due date: 2026-10-30', 'Purchase order: PO-OK',
             '', 'Description       Quantity       Unit price       Line total',
             'Paper                    3              10.00              30.00',
             'Folders                  2              10.00              20.00',
             '', 'Subtotal before discount and tax: 50.00']
    content = DecodedStreamObject()
    content.set_data(('BT /F1 12 Tf 48 744 Td 24 TL '
                      + ' '.join(f'({line}) Tj T*' for line in lines) + ' ET').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(content)
    writer.write(source)
    output = directory / 'exports'
    schema = invoice_review_schema()
    schema['fields']['invoice_number'] = {'type': 'string', 'required': True}
    source_values = deepcopy(SOURCE_VALUES)
    accepted_values = deepcopy(ACCEPTED_VALUES)
    fields = deepcopy(EXPORT_FIELDS)
    if extended_rules:
        schema['fields'].update({'issued': {'type': 'date', 'label': 'Invoice date'},
                                 'due': {'type': 'date', 'label': 'Due date'},
                                 'has_po': {'type': 'boolean', 'label': 'Purchase order required'},
                                 'po_number': {'type': 'string', 'label': 'Purchase order number'}})
        schema['business_validation']['rules'].extend([
            {'id': 'invoice_dates', 'validator': 'date_order:v1', 'earlier': '/issued', 'later': '/due', 'severity': 'blocking'},
            {'id': 'purchase_order', 'validator': 'required_if:v1', 'when': '/has_po', 'equals': True,
             'required': ['/po_number'], 'severity': 'blocking'},
        ])
        source_values.update(issued='2026-10-30', due='2026-10-01', has_po=True, po_number='')
        accepted_values.update(issued='2026-10-01', due='2026-10-30', has_po=True, po_number='PO-OK')
        fields.update({key: {'alias': key, 'type': 'bool' if key == 'has_po' else 'str'}
                       for key in ('issued', 'due', 'has_po', 'po_number')})
    if not with_rules:
        del schema['business_validation']
    with managed_connect(config) as conn:
        forms = ReviewSchemaVersionService(conn)
        form = forms.create_template(schema_key='invoice-acceptance', name='Invoice acceptance',
                                     initial_schema=schema, user='admin')['template']
        schema_version = forms.publish(form['id'], expected_revision=1, user='admin')['version']
        forms.update_template(form['id'], status='active', user='admin')
        definition = {'schema_version': 1, 'pipeline': ['extract', 'review', 'json', 'csv', 'pdf'], 'tasks': {
            'extract': {'module': 'standard_step.extraction.extract_pdf', 'class': 'ExtractPdfTask',
                        'params': {'api_key': {'$secret': 'synthetic-extract'}, 'fields': fields}, 'on_error': 'stop'},
            'review': {'module': 'standard_step.review.review_gate', 'class': 'ReviewGateTask', 'on_error': 'stop',
                       'params': {'schema_version_id': schema_version['id'], 'review_scope': 'document', 'always_review': not with_rules}},
            'json': {'module': 'standard_step.storage.store_metadata_as_json', 'class': 'StoreMetadataAsJson',
                     'params': {'data_dir': str(output), 'filename': filename_template, 'extraction': {'fields': fields}}},
            'csv': {'module': 'standard_step.storage.store_metadata_as_csv', 'class': 'StoreMetadataAsCsv',
                    'params': {'data_dir': str(output), 'filename': filename_template, 'extraction': {'fields': fields}}},
            'pdf': {'module': 'standard_step.storage.store_file_to_localdrive', 'class': 'StoreFileToLocaldrive',
                    'params': {'files_dir': str(output), 'filename': filename_template, 'extraction': {'fields': fields}}},
        }}
        pipelines = PipelineTemplateService(conn, configured_secret_aliases={'synthetic-extract'})
        template = pipelines.create_template(template_key='invoice-acceptance', name='Invoice acceptance',
                                             initial_definition=definition, user='admin')['template']
        version = pipelines.publish(template['id'], expected_revision=1, user='admin')['version']
        pipelines.update_template(template['id'], status='active', user='admin')
        created = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=version['id'], role='operator', source='web', assignment_source='upload',
            files=[{'file_path': str(source), 'original_filename': source.name, 'status': 'queued'}], user='operator',
        )
    return {'document': created['documents'][0], 'batch': created['batch'], 'schema': schema,
            'schema_version': schema_version, 'form': form, 'pipeline': version, 'source': source, 'output': output,
            'source_values': source_values, 'accepted_values': accepted_values}


def run_invoice_workflow(config: TempConfig, case: dict[str, Any]) -> dict[str, Any]:
    """Execute the pinned definition through the real workflow runner."""
    document = case['document']
    with managed_connect(config) as conn:
        executable = PipelineDefinitionService(conn, config).load_for_document(document['id'])
    flow = WorkflowLoader(config, definition=executable.definition, pipeline_version_id=executable.version_id,
                          pipeline_template_id=executable.template_id).load_workflow()
    assert flow is not None
    return flow({'id': document['id'], 'document_id': document['id'], 'batch_id': document['batch_id'],
                 'file_path': str(case['source']), 'original_filename': case['source'].name})


@contextmanager
def offline_invoice_workflows(source_values: dict[str, Any] | None = None) -> Iterator[list[dict[str, Any]]]:
    """Replace only extraction, orchestration wrappers, and destructive cleanup."""
    calls: list[dict[str, Any]] = []

    class SyntheticExtraction(BaseTask):
        def on_start(self, context: dict[str, Any]) -> None:
            self.initialize_context(context)

        def validate_required_fields(self, context: dict[str, Any]) -> None:
            return None

        def run(self, context: dict[str, Any]) -> dict[str, Any]:
            data = deepcopy(SOURCE_VALUES if source_values is None else source_values)
            calls.append({'document_id': context['document_id'], 'task_run_id': context['task_run_id']})
            with managed_connect(self.config_manager) as conn:
                extractions = ExtractionRepository(conn)
                result = extractions.save_result(document_id=context['document_id'], task_run_id=context['task_run_id'],
                                                  provider='synthetic', data=data)
                extractions.save_fields(document_id=context['document_id'], extraction_result_id=result['id'], fields=[
                    {'field_key': key, 'extracted_value': value, 'confidence': .99} for key, value in data.items()
                ])
            context['data'] = data
            return context

    class PreserveSyntheticInput(SyntheticExtraction):
        def run(self, context: dict[str, Any]) -> dict[str, Any]:
            return context

    original_import = WorkflowLoader._import_task_class

    def import_task(loader: WorkflowLoader, module_name: str, class_name: str) -> type[BaseTask]:
        if (module_name, class_name) == ('standard_step.extraction.extract_pdf', 'ExtractPdfTask'):
            return SyntheticExtraction
        return original_import(loader, module_name, class_name)

    def flow_decorator(*_args: Any, **_kwargs: Any) -> Any:
        return lambda function: function

    def task_decorator(*_args: Any, **_kwargs: Any) -> Any:
        def decorate(function: Any) -> Any:
            return lambda *args, **kwargs: {'result': function(*args, **kwargs)}
        return decorate

    logger = type('SyntheticLogger', (), {'info': lambda *_args, **_kwargs: None})()
    with patch.object(WorkflowLoader, '_import_task_class', import_task), \
            patch('modules.workflow_loader.CleanupTask', PreserveSyntheticInput), \
            patch('modules.workflow_loader.flow', flow_decorator), \
            patch('modules.workflow_loader.task', task_decorator), \
            patch('modules.workflow_loader.get_run_logger', lambda: logger):
        yield calls
