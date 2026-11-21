"""Lightweight collaboration contract. No geometry or material source of truth."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from enrealworld.validation_model import Model, Identifier

Text = Annotated[str, Field(min_length=1)]


# Directions are read as: subject A <relation> target B.
RELATION_VOCABULARY = {
    'supported_by': 'B supports A',
    'connected_to': 'A and B are connected (symmetric)',
    'inside': 'A is inside B',
    'contact': 'A and B are in contact (symmetric)',
    'grasped_by': 'B grasps A',
    'attached_to': 'A is attached to anchor B',
}


class ImplementationUnit(Model):
    id: Identifier
    file: Text
    symbol: Text  # qualified function/class or named construction step, never a line number
    purpose: Literal['geometry', 'physics', 'control', 'construction', 'other'] = 'construction'


class Claim(Model):
    id: Identifier
    statement: Text
    kind: Literal['observation', 'requirement', 'assumption']
    phases: list[Text] = Field(min_length=1)
    source_refs: list[Text] = Field(min_length=1)
    implementation_refs: list[Identifier] = Field(default_factory=list)
    test_refs: list[Text] = Field(default_factory=list)


class Entity(Model):
    id: Identifier
    role: Text
    physical_kind: Literal['rigid', 'soft', 'fluid', 'granular', 'mixed', 'unknown'] = 'unknown'
    requirements: list[Claim] = Field(default_factory=list)
    implementation_refs: list[Identifier] = Field(default_factory=list)


class Relation(Claim):
    subject: Identifier
    target: Identifier
    relation: str = Field(
        min_length=1, pattern=r"\S",
        description="Recommended vocabulary with subject A / target B direction: "
                    + "; ".join(f"{key}: {meaning}" for key, meaning in RELATION_VOCABULARY.items())
                    + ". Custom relations are allowed; explain their meaning and A/B direction in statement.",
        examples=list(RELATION_VOCABULARY),
        json_schema_extra={'x-recommended-relations': RELATION_VOCABULARY},
    )


class CollaborationGraph(Model):
    schema_version: Literal['1'] = '1'
    scene_id: Identifier
    revision: Annotated[int, Field(ge=1)] = 1
    entities: list[Entity] = Field(min_length=1)
    relations: list[Relation] = Field(default_factory=list)
    implementation_units: list[ImplementationUnit] = Field(default_factory=list)

    @model_validator(mode='after')
    def references(self):
        claims = [c for e in self.entities for c in e.requirements] + self.relations
        ids = [e.id for e in self.entities] + [c.id for c in claims]
        units = [u.id for u in self.implementation_units]
        if len(ids) != len(set(ids)) or len(units) != len(set(units)):
            raise ValueError('duplicate graph or implementation ID')
        entities = {e.id for e in self.entities}
        for r in self.relations:
            if r.subject not in entities or r.target not in entities:
                raise ValueError('unknown relation endpoint')
        for item in [*self.entities, *claims]:
            if set(item.implementation_refs) - set(units):
                raise ValueError('unknown implementation unit')
        for unit in self.implementation_units:
            from pathlib import PurePosixPath
            p = PurePosixPath(unit.file)
            if p.is_absolute() or '..' in p.parts:
                raise ValueError('implementation file must be project relative')
        return self


def main():
    """Check the adjacent JSON schema or export it to an explicit directory."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=main.__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--output', type=Path)
    args = parser.parse_args()
    name = 'collaboration-graph.schema.json'
    schema = CollaborationGraph.model_json_schema()
    if args.check:
        if json.loads(Path(__file__).with_name(name).read_text()) != schema:
            raise SystemExit('schema drift: collaboration-graph')
        print('Packaged scene graph schema matches Python model')
    else:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/name).write_text(json.dumps(schema, indent=2) + '\n')


if __name__ == '__main__':
    main()
