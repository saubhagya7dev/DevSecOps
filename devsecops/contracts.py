"""Strict JSON contracts used at each model boundary."""
S = {'type': 'string'}
I = {'type': 'integer'}


def array(items):
    return {'type': 'array', 'items': items}


def obj(**properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


PROFILE = obj(
    summary=S,
    technologies=array(obj(name=S, version=S, evidence_ids=array(S))),
    components=array(obj(name=S, description=S, evidence_ids=array(S))),
    observations=array(obj(id=S, claim=S, path=S, start_line=I, end_line=I, quote=S,
                           kind={'type': 'string', 'enum': ['observed', 'inferred']})),
    research_questions=array(S), unknowns=array(S),
)

INCIDENTS = obj(incidents=array(obj(
    id=S, title=S, source_id=S, source_quote=S,
    publication_date=S, incident_date=S, victim=S,
    source_type={'type': 'string', 'enum': ['observed attack', 'vulnerability advisory', 'background guidance']},
    mechanism=S, prerequisites=array(S), technologies=array(S), mitigations=array(S), unknowns=array(S),
)), research_limitations=array(S))

REVIEW = obj(
    summary=S,
    findings=array(obj(
        id=S, title=S,
        classification={'type': 'string', 'enum': ['Supported concern', 'Needs verification', 'Background lesson']},
        impact={'type': 'string', 'enum': ['High', 'Medium', 'Low']},
        confidence={'type': 'string', 'enum': ['High', 'Medium', 'Low']},
        incident_ids=array(S), evidence_ids=array(S), mechanism=S, prerequisite=S,
        reasoning=S, counterevidence=S, missing_information=array(S),
        action=S, verification=S,
    )),
    existing_defenses=array(obj(description=S, evidence_ids=array(S))),
    rejected_matches=array(obj(incident_id=S, reason=S)),
    questions=array(S),
    followup_requests=array(obj(target={'type': 'string', 'enum': ['analyst', 'researcher']}, question=S)),
)

FOLLOWUP = obj(answer=S, evidence_ids=array(S), incident_ids=array(S), unknowns=array(S))


def validate_shape(value, schema, path='$'):
    """Validate the supported schema subset locally, even when the provider is mocked."""
    kind = schema['type']
    expected = {'object': dict, 'array': list, 'string': str, 'integer': int}[kind]
    if not isinstance(value, expected) or (kind == 'integer' and isinstance(value, bool)):
        raise ValueError(f'Invalid agent handoff at {path}: expected {kind}.')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'Invalid enum at {path}.')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError(f'Unexpected or missing agent fields at {path}.')
        for key, child in schema['properties'].items():
            validate_shape(value[key], child, path + '.' + key)
    if kind == 'array':
        if len(value) > 100:
            raise ValueError('Agent handoff exceeds item budget.')
        for i, child in enumerate(value):
            validate_shape(child, schema['items'], f'{path}[{i}]')
    if kind == 'string' and len(value) > 15_000:
        raise ValueError('Agent handoff exceeds string budget.')
