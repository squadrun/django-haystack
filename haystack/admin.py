# encoding: utf-8

from __future__ import absolute_import, division, print_function, unicode_literals

import re

from django.contrib.admin.options import ModelAdmin
from django.contrib.admin.views.main import ChangeList, SEARCH_VAR
from django.core.paginator import InvalidPage, Paginator

from haystack import connections
from haystack.query import SearchQuerySet
from haystack.inputs import Raw

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_unicode as force_text


def list_max_show_all(changelist):
    """
    Returns the maximum amount of results a changelist can have for the
    "Show all" link to be displayed in a manner compatible with both Django
    1.4 and 1.3. See Django ticket #15997 for details.
    """
    try:
        # This import is available in Django 1.3 and below
        from django.contrib.admin.views.main import MAX_SHOW_ALL_ALLOWED
        return MAX_SHOW_ALL_ALLOWED
    except ImportError:
        return changelist.list_max_show_all


class SearchChangeList(ChangeList):
    def __init__(self, *args, **kwargs):
        self.haystack_connection = kwargs.pop('haystack_connection', 'default')
        super(SearchChangeList, self).__init__(*args, **kwargs)

    def custom_get_filters(self, request):
        indexed_model = connections['default'].get_unified_index().get_index(self.model)
        list_filter = self.list_filter
        # dict of filtered index name and the model attribute they map to
        filter_name_and_model_attr_map = {}
        for name, field in indexed_model.fields.items():
            filter_name_and_model_attr_map[name] = field.model_attr

        indexed_field_and_value_map = {}
        pattern_exact = re.compile('__exact$')

        # remove '__exact' from all query params, and get the filtered indexed name for the resulting query param
        # if the filtered indexed name is present in the `list_filters` for the admin class, add it to final filters
        for query, value in request.GET.items():
            filter_field_name = pattern_exact.sub('', query)
            indexed_field = next((name for name, model_attr in filter_name_and_model_attr_map.items() if
                                  model_attr == filter_field_name), None)
            if indexed_field and indexed_field in list_filter:
                indexed_field_and_value_map[indexed_field] = value

        return indexed_field_and_value_map

    def get_results(self, request):
        if SEARCH_VAR not in request.GET or (len(request.GET[SEARCH_VAR]) is 0 and len(request.GET.keys()) is 1):
            return super(SearchChangeList, self).get_results(request)

        filters = self.custom_get_filters(request)

        # Note that pagination is 0-based, not 1-based.
        sqs = SearchQuerySet(self.haystack_connection).models(self.model)
        if request.GET[SEARCH_VAR]:
            sqs = sqs.filter(text=Raw('*{}*'.format(request.GET[SEARCH_VAR])))
        if filters:
            sqs = sqs.filter(**filters)

        sqs = sqs.load_all()

        paginator = Paginator(sqs, self.list_per_page)
        # Get the number of objects, with admin filters applied.
        result_count = paginator.count
        full_result_count = SearchQuerySet(self.haystack_connection).models(self.model).all().count()

        can_show_all = result_count <= list_max_show_all(self)
        multi_page = result_count > self.list_per_page

        # Get the list of objects to display on this page.
        try:
            result_list = paginator.page(self.page_num + 1).object_list
            # Grab just the Django models, since that's what everything else is
            # expecting.
            result_list = [result.object for result in result_list]
        except InvalidPage:
            result_list = ()

        self.result_count = result_count
        self.full_result_count = full_result_count
        self.result_list = result_list
        self.can_show_all = can_show_all
        self.multi_page = multi_page
        self.paginator = paginator


class SearchModelAdminMixin(object):
    # haystack connection to use for searching
    haystack_connection = 'default'

    def get_changelist(self, request, **kwargs):
        return SearchChangeList


class SearchModelAdmin(SearchModelAdminMixin, ModelAdmin):
    pass
