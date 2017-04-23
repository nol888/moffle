from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms import StringField
from wtforms.validators import DataRequired


class SearchForm(FlaskForm):
    text = StringField('text', validators=[DataRequired()])
    network = StringField('network', validators=[DataRequired()])
    channel = StringField('channel', validators=[DataRequired()])
    author = StringField('author')


class AjaxSearchForm(SearchForm):
    segment = IntegerField('segment', default=0)
