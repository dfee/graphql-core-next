import re
from itertools import chain
from typing import Any, Callable, Dict, List, Optional, Union, cast

from ..language import print_ast
from ..pyutils import is_invalid, is_nullish
from ..type import (
    DEFAULT_DEPRECATION_REASON, GraphQLArgument,
    GraphQLDirective, GraphQLEnumType, GraphQLEnumValue, GraphQLField,
    GraphQLInputObjectType, GraphQLInputType, GraphQLInterfaceType,
    GraphQLNamedType, GraphQLObjectType, GraphQLScalarType, GraphQLSchema,
    GraphQLString, GraphQLUnionType, is_enum_type, is_input_object_type,
    is_interface_type, is_introspection_type, is_object_type, is_scalar_type,
    is_specified_directive, is_specified_scalar_type, is_union_type)
from .ast_from_value import ast_from_value

__all__ = [
    'print_schema', 'print_introspection_schema', 'print_type', 'print_value']


def print_schema(schema: GraphQLSchema) -> str:
    return print_filtered_schema(
        schema, lambda n: not is_specified_directive(n), is_defined_type)


def print_introspection_schema(schema: GraphQLSchema) -> str:
    return print_filtered_schema(
        schema, is_specified_directive, is_introspection_type)


def is_defined_type(type_: GraphQLNamedType) -> bool:
    return (not is_specified_scalar_type(type_) and
            not is_introspection_type(type_))


def print_filtered_schema(
        schema: GraphQLSchema,
        directive_filter: Callable[[GraphQLDirective], bool],
        type_filter: Callable[[GraphQLNamedType], bool]) -> str:
    directives = filter(directive_filter, schema.directives)
    type_map = schema.type_map
    types = filter(  # type: ignore
        type_filter, map(type_map.get, sorted(type_map)))

    return '\n\n'.join(chain(filter(None, [
        print_schema_definition(schema)]),
        (print_directive(directive) for directive in directives),
        (print_type(type_) for type_ in types))) + '\n'   # type: ignore


def print_schema_definition(schema: GraphQLSchema) -> Optional[str]:
    if is_schema_of_common_names(schema):
        return None

    operation_types = []

    query_type = schema.query_type
    if query_type:
        operation_types.append(f'  query: {query_type.name}')

    mutation_type = schema.mutation_type
    if mutation_type:
        operation_types.append(f'  mutation: {mutation_type.name}')

    subscription_type = schema.subscription_type
    if subscription_type:
        operation_types.append(f'  subscription: {subscription_type.name}')

    return 'schema {\n' + '\n'.join(operation_types) + '\n}'


def is_schema_of_common_names(schema: GraphQLSchema) -> bool:
    """Check whether this schema uses the common naming convention.

    GraphQL schema define root types for each type of operation. These types
    are the same as any other type and can be named in any manner, however
    there is a common naming convention:

    schema {
      query: Query
      mutation: Mutation
    }

    When using this naming convention, the schema description can be omitted.
    """
    query_type = schema.query_type
    if query_type and query_type.name != 'Query':
        return False

    mutation_type = schema.mutation_type
    if mutation_type and mutation_type.name != 'Mutation':
        return False

    subscription_type = schema.subscription_type
    if subscription_type and subscription_type.name != 'Subscription':
        return False

    return True


def print_type(type_: GraphQLNamedType) -> str:
    if is_scalar_type(type_):
        type_ = cast(GraphQLScalarType, type_)
        return print_scalar(type_)
    if is_object_type(type_):
        type_ = cast(GraphQLObjectType, type_)
        return print_object(type_)
    if is_interface_type(type_):
        type_ = cast(GraphQLInterfaceType, type_)
        return print_interface(type_)
    if is_union_type(type_):
        type_ = cast(GraphQLUnionType, type_)
        return print_union(type_)
    if is_enum_type(type_):
        type_ = cast(GraphQLEnumType, type_)
        return print_enum(type_)
    if is_input_object_type(type_):
        type_ = cast(GraphQLInputObjectType, type_)
        return print_input_object(type_)
    raise TypeError(f'Unknown type: {type_!r}')


def print_scalar(type_: GraphQLScalarType) -> str:
    return print_description(type_) + f'scalar {type_.name}'


def print_object(type_: GraphQLObjectType) -> str:
    interfaces = type_.interfaces
    implemented_interfaces = (
            ' implements ' + ' & '.join(i.name for i in interfaces)
        ) if interfaces else ''
    return (print_description(type_) +
            f'type {type_.name}{implemented_interfaces} ' +
            '{\n' + print_fields(type_) + '\n}')


def print_interface(type_: GraphQLInterfaceType) -> str:
    return (print_description(type_) +
            f'interface {type_.name} ' +
            '{\n' + print_fields(type_) + '\n}')


def print_union(type_: GraphQLUnionType) -> str:
    return (print_description(type_) +
            f'union {type_.name} = ' + ' | '.join(
                t.name for t in type_.types))


def print_enum(type_: GraphQLEnumType) -> str:
    return (print_description(type_) +
            f'enum {type_.name} ' +
            '{\n' + print_enum_values(type_.values) + '\n}')


def print_enum_values(values: Dict[str, GraphQLEnumValue]) -> str:
    return '\n'.join(
        print_description(value, '  ', not i) +
        f'  {name}' + print_deprecated(value)
        for i, (name, value) in enumerate(values.items()))


def print_input_object(type_: GraphQLInputObjectType) -> str:
    fields = type_.fields.items()
    return (print_description(type_) +
            f'input {type_.name} ' + '{\n' +
            '\n'.join(
                print_description(field, '  ', not i) + '  ' +
                print_input_value(name, field)
                for i, (name, field) in enumerate(fields)) + '\n}')


def print_fields(type_: Union[GraphQLObjectType, GraphQLInterfaceType]) -> str:
    fields = type_.fields.items()
    return '\n'.join(
        print_description(field, '  ', not i) + f'  {name}' +
        print_args(field.args, '  ') + f': {field.type}' +
        print_deprecated(field)
        for i, (name, field) in enumerate(fields))


def print_args(args: Dict[str, GraphQLArgument], indentation='') -> str:
    if not args:
        return ''

    # If every arg does not have a description, print them on one line.
    if not any(arg.description for arg in args.values()):
        return '(' + ', '.join(
            print_input_value(name, arg) for name, arg in args.items()) + ')'

    return ('(\n' + '\n'.join(
        print_description(arg, f'  {indentation}', not i) +
        f'  {indentation}' + print_input_value(name, arg)
        for i, (name, arg) in enumerate(args.items())) + f'\n{indentation})')


def print_input_value(name: str, arg: GraphQLArgument) -> str:
    arg_decl = f'{name}: {arg.type}'
    if not is_invalid(arg.default_value):
        arg_decl += f' = {print_value(arg.default_value, arg.type)}'
    return arg_decl


def print_directive(directive: GraphQLDirective) -> str:
    return (print_description(directive) +
            f'directive @{directive.name}' +
            print_args(directive.args) +
            ' on ' + ' | '.join(
                location.name for location in directive.locations))


def print_deprecated(
        field_or_enum_value: Union[GraphQLField, GraphQLEnumValue]) -> str:
    if not field_or_enum_value.is_deprecated:
        return ''
    reason = field_or_enum_value.deprecation_reason
    if (is_nullish(reason) or reason == '' or
            reason == DEFAULT_DEPRECATION_REASON):
        return ' @deprecated'
    else:
        return f' @deprecated(reason: {print_value(reason, GraphQLString)})'


def print_description(
        type_: Union[GraphQLArgument, GraphQLDirective,
                     GraphQLEnumValue, GraphQLNamedType],
        indentation='', first_in_block=True) -> str:
    if not type_.description:
        return ''
    lines = description_lines(type_.description, 120 - len(indentation))

    description = []
    if indentation and not first_in_block:
        description.append('\n')
    description.extend([indentation, '"""'])

    if len(lines) == 1 and len(lines[0]) < 70 and not lines[0].endswith('"'):
        # In some circumstances, a single line can be used for the description.
        description.extend([escape_quote(lines[0]), '"""\n'])
    else:
        # Format a multi-line block quote to account for leading space.
        has_leading_space = lines and lines[0].startswith((' ', '\t'))
        if not has_leading_space:
            description.append('\n')
        for i, line in enumerate(lines):
            if i or not has_leading_space:
                description.append(indentation)
            description.extend([escape_quote(line), '\n'])
        description.extend([indentation, '"""\n'])

    return ''.join(description)


def escape_quote(line: str) -> str:
    return line.replace('"""', '\\"""')


def description_lines(description: str, max_len: int) -> List[str]:
    lines: List[str] = []
    append_line, extend_lines = lines.append, lines.extend
    raw_lines = description.splitlines()
    for raw_line in raw_lines:
        if raw_line:
            # For > 120 character long lines, cut at space boundaries into
            # sublines of ~80 chars.
            extend_lines(break_line(raw_line, max_len))
        else:
            append_line(raw_line)
    return lines


def break_line(line: str, max_len: int) -> List[str]:
    if len(line) < max_len + 5:
        return [line]
    parts = re.split(f'((?: |^).{{15,{max_len - 40}}}(?= |$))', line)
    if len(parts) < 4:
        return [line]
    sublines = [parts[0] + parts[1] + parts[2]]
    append_subline = sublines.append
    for i in range(3, len(parts), 2):
        append_subline(parts[i][1:] + parts[i + 1])
    return sublines


def print_value(value: Any, type_: GraphQLInputType) -> str:
    """Convenience function for printing a Python value"""
    return print_ast(ast_from_value(value, type_))  # type: ignore
