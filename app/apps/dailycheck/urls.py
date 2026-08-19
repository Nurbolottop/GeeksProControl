from django.urls import path

from apps.dailycheck import views

app_name = "dailycheck"

urlpatterns = [
    path("", views.index, name="index"),
    path("items/create/", views.item_create, name="item_create"),
    path("items/<int:pk>/delete/", views.item_delete, name="item_delete"),
    path("items/<int:pk>/toggle/", views.toggle, name="toggle"),
    path("items/<int:pk>/note/", views.note, name="note"),
    path("projects/<int:pk>/items/create/", views.project_item_create,
         name="project_item_create"),
    path("project-items/<int:pk>/toggle/", views.project_toggle,
         name="project_toggle"),
    path("project-items/<int:pk>/note/", views.project_note,
         name="project_note"),
    path("project-items/<int:pk>/delete/", views.project_item_delete,
         name="project_item_delete"),
]
