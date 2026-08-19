from django.urls import path

from apps.dailycheck import views

app_name = "dailycheck"

urlpatterns = [
    path("", views.index, name="index"),
    path("items/create/", views.item_create, name="item_create"),
    path("items/<int:pk>/delete/", views.item_delete, name="item_delete"),
    path("items/<int:pk>/toggle/", views.toggle, name="toggle"),
    path("items/<int:pk>/note/", views.note, name="note"),
]
