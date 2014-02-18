import inspect
import os

from xml.sax.saxutils import escape

cwd = os.path.split(os.path.abspath(
    inspect.getfile(inspect.currentframe())))[0]


def load_template(namespace, name):
    template_name = os.path.join(cwd, namespace, name)
    f = open(template_name)
    text = f.read()
    f.close()
    return text


def populate_template(template, escape_variables, no_escape_variables=None):
    variables = {
        name: escape(
            str(variable)) for name, variable in escape_variables.items()}
    if no_escape_variables:
        variables.update(no_escape_variables)

    return template.format(**variables)