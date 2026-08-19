from django.urls import path

from apps.dailycheck import views

app_name = "dailycheck"

urlpatterns = [
    path("projects/<int:pk>/items/create/", views.project_item_create,
         name="project_item_create"),
    path("project-items/<int:pk>/toggle/", views.project_toggle,
         name="project_toggle"),
    path("project-items/<int:pk>/note/", views.project_note,
         name="project_note"),
    path("project-items/<int:pk>/delete/", views.project_item_delete,
         name="project_item_delete"),
]
