import inspect
import os

from xml.sax.saxutils import escape

cwd = os.path.split(os.path.abspath(
    inspect.getfile(inspect.currentframe())))[0]


def load_template(namespace, name):
    template_name = os.path.join(cwd, namespace, name)
    return open(template_name).read()


def populate_template(template, escape_variables, no_escape_variables=None):
    variables = {
        name: escape(
            str(variable)) for name, variable in escape_variables.items()}
    if no_escape_variables:
        variables.update(no_escape_variables)

    return template.format(**variables)


def iter_populate_template(template_path, data):
    """
    data = [({...}:escape_dict, {...}:nonescape_dict), ...]
    """

    result = []
    template = load_template(*template_path)

    for escape_dict, nonescape_dict in data:
        result.append(populate_template(template, escape_dict, nonescape_dict))

    return ''.join(result)
