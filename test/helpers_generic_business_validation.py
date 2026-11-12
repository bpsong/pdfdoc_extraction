"""Synthetic document scenarios through real publication, review, and exports."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from modules.db.connection import managed_connect
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from test.helpers_sqlite import TempConfig


def comparison(left: str, right: str, *, collection: str | None = None) -> dict[str, Any]:
    scope = 'row' if collection else 'document'
    rule: dict[str, Any] = {
        'id': 'limit', 'validator': 'compare_number:v1', 'severity': 'blocking',
        'left': {'kind': 'field', 'scope': scope, 'field': left}, 'operator': 'lte',
        'right': {'kind': 'field', 'scope': scope, 'field': right},
    }
    if collection:
        rule.update(scope='rows', collection=collection)
    return rule


def document_scenario(kind: str) -> dict[str, Any]:
    """Return unrelated domain keys to expose hidden invoice assumptions."""
    if kind == 'shipping':
        fields = {'reference': {'type': 'string', 'label': 'Shipment reference', 'required': True},
                  'packages': {'type': 'array', 'label': 'Packages', 'items': {'type': 'object', 'properties': {
                      name: {'type': 'number', 'label': label} for name, label in (
                          ('count', 'Package count'), ('weight_each', 'Weight per package'), ('weight', 'Row weight'),
                          ('delivered', 'Delivered quantity'), ('ordered', 'Ordered quantity'))}}},
                  'total_weight': {'type': 'number', 'label': 'Declared weight'},
                  'hazardous': {'type': 'boolean', 'label': 'Hazardous goods'},
                  'un_number': {'type': 'string', 'label': 'UN number'}}
        accepted = {'reference': 'SHIP-TEST', 'packages': [
            {'count': 2, 'weight_each': 3, 'weight': 6, 'delivered': 5, 'ordered': 5},
            {'count': 1, 'weight_each': 4, 'weight': 4, 'delivered': 1, 'ordered': 1}],
            'total_weight': 10, 'hazardous': True, 'un_number': 'UN1234'}
        rules = [comparison('/delivered', '/ordered', collection='/packages'),
                 {'id': 'weight', 'validator': 'line_amount:v1', 'collection': '/packages',
                  'quantity': '/count', 'unit_price': '/weight_each', 'line_total': '/weight'},
                 {'id': 'total', 'validator': 'sum_equals:v1', 'collection': '/packages',
                  'item_value': '/weight', 'target': '/total_weight', 'severity': 'blocking'},
                 {'id': 'danger', 'validator': 'required_if:v1', 'when': '/hazardous', 'equals': True,
                  'required': ['/un_number'], 'severity': 'blocking'}]
        extracted = deepcopy(accepted)
        extracted['packages'][0]['delivered'] = 6
    elif kind == 'insurance':
        fields = {name: {'type': field_type, 'label': label} for name, field_type, label in (
            ('reference', 'string', 'Policy reference'), ('effective', 'date', 'Effective date'),
            ('expiry', 'date', 'Expiry date'), ('covered', 'number', 'Covered amount'),
            ('limit', 'number', 'Policy limit'), ('has_endorsement', 'boolean', 'Has endorsement'),
            ('endorsement', 'string', 'Endorsement reference'))}
        accepted = {'reference': 'POLICY-TEST', 'effective': '2026-11-01', 'expiry': '2027-11-01',
                    'covered': 100, 'limit': 200, 'has_endorsement': True, 'endorsement': 'ENDORSEMENT-1'}
        rules = [comparison('/covered', '/limit'),
                 {'id': 'dates', 'validator': 'date_order:v1', 'earlier': '/effective', 'later': '/expiry', 'severity': 'blocking'},
                 {'id': 'endorsement', 'validator': 'required_if:v1', 'when': '/has_endorsement', 'equals': True,
                  'required': ['/endorsement'], 'severity': 'blocking'}]
        extracted = {**accepted, 'expiry': '2026-10-01', 'endorsement': ''}
    elif kind == 'invoice':
        fields = {'reference': {'type': 'string', 'label': 'Invoice reference'},
                  'lines': {'type': 'array', 'label': 'Line items', 'items': {'type': 'object', 'properties': {
                      name: {'type': 'number'} for name in ('quantity', 'price', 'amount')}}},
                  'subtotal': {'type': 'number'}}
        accepted = {'reference': 'INVOICE-TEST', 'lines': [{'quantity': 2, 'price': 10, 'amount': 20}], 'subtotal': 20}
        rules = [{'id': 'line', 'validator': 'line_amount:v1', 'collection': '/lines',
                  'quantity': '/quantity', 'unit_price': '/price', 'line_total': '/amount'},
                 {'id': 'subtotal', 'validator': 'sum_equals:v1', 'collection': '/lines',
                  'item_value': '/amount', 'target': '/subtotal', 'severity': 'blocking'}]
        extracted = deepcopy(accepted)
        extracted['lines'][0]['amount'] = 21
    else:
        raise ValueError('Unknown synthetic scenario.')
    return {'schema': {'title': f'Synthetic {kind}', 'fields': fields, 'business_validation': {'rules': rules}},
            'source_values': extracted, 'accepted_values': accepted}


def create_generic_workflow(
    config: TempConfig, directory: Path, kind: str, *, schema_version: dict[str, Any] | None = None,
    with_rules: bool = True,
) -> dict[str, Any]:
    """Publish normal task versions and create a queued synthetic document."""
    scenario = document_scenario(kind)
    if not with_rules:
        del scenario['schema']['business_validation']
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f'synthetic-{kind}.pdf'
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
        NameObject('/F1'): DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                           NameObject('/Subtype'): NameObject('/Type1'),
                                           NameObject('/BaseFont'): NameObject('/Helvetica')})})})
    lines = [f'SYNTHETIC {kind.upper()} - TEST DATA ONLY']
    for key, value in scenario['accepted_values'].items():
        if isinstance(value, list):
            for index, row in enumerate(value):
                lines.append(f'{key} row {index + 1}')
                lines.extend(f'  {name}: {item}' for name, item in row.items())
        else:
            lines.append(f'{key}: {value}')
    stream = DecodedStreamObject()
    text = 'BT /F1 10 Tf 30 744 Td 28 TL ' + ' '.join(
        '(' + line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ') Tj T*' for line in lines) + ' ET'
    stream.set_data(text.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(source)
    fields: dict[str, Any] = {}
    for key, field in scenario['schema']['fields'].items():
        field_type = field['type']
        fields[key] = {'alias': key, 'type': {'number': 'float', 'boolean': 'bool', 'array': 'List[Any]'}.get(field_type, 'str')}
        if field_type == 'array':
            fields[key].update(is_table=True, item_fields={
                name: {'alias': name, 'type': 'float'} for name in field['items']['properties']})
    output = directory / 'exports'
    with managed_connect(config) as conn:
        forms = ReviewSchemaVersionService(conn)
        if schema_version is None:
            form = forms.create_template(schema_key=f'generic-{kind}', name=f'Synthetic {kind}',
                                         initial_schema=scenario['schema'], user='admin')['template']
            schema_version = forms.publish(form['id'], expected_revision=1, user='admin')['version']
        assert schema_version is not None
        forms.update_template(schema_version['schema_template_id'], status='active', user='admin')
        tasks = {
            'extract': {'module': 'standard_step.extraction.extract_pdf', 'class': 'ExtractPdfTask',
                        'params': {'api_key': {'$secret': 'synthetic-extract'}, 'fields': fields}},
            'review': {'module': 'standard_step.review.review_gate', 'class': 'ReviewGateTask',
                       'params': {'schema_version_id': schema_version['id'], 'always_review': True, 'review_scope': 'document'}},
            'json': {'module': 'standard_step.storage.store_metadata_as_json', 'class': 'StoreMetadataAsJson',
                     'params': {'data_dir': str(output), 'filename': '{reference}_{id}', 'extraction': {'fields': fields}}},
            'csv': {'module': 'standard_step.storage.store_metadata_as_csv', 'class': 'StoreMetadataAsCsv',
                    'params': {'data_dir': str(output), 'filename': '{reference}_{id}', 'extraction': {'fields': fields}}},
            'pdf': {'module': 'standard_step.storage.store_file_to_localdrive', 'class': 'StoreFileToLocaldrive',
                    'params': {'files_dir': str(output), 'filename': '{reference}_{id}'}},
        }
        pipelines = PipelineTemplateService(conn, configured_secret_aliases={'synthetic-extract'})
        template = pipelines.create_template(template_key=f'generic-{kind}', name=f'Synthetic {kind}',
            initial_definition={'schema_version': 1, 'pipeline': list(tasks), 'tasks': tasks}, user='admin')['template']
        pipeline = pipelines.publish(template['id'], expected_revision=1, user='admin')['version']
        pipelines.update_template(template['id'], status='active', user='admin')
        created = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=pipeline['id'], role='operator', source='web', assignment_source='upload',
            files=[{'file_path': str(source), 'original_filename': source.name, 'status': 'queued'}], user='operator')
    return {**scenario, 'source': source, 'output': output, 'pipeline': pipeline,
            'document': created['documents'][0], 'schema_version': schema_version}
