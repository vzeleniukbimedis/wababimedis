from flask import Blueprint

interactive_blueprint = Blueprint("interactive", __name__)

from . import routes
