from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    TemplateView,
    ListView,
)


class LogListView(LoginRequiredMixin, TemplateView):
    template_name = 'learning/log_list.html'
