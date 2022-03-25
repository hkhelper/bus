from django.urls import path

from . import views

app_name = 'hkzh'
urlpatterns = [
    path('', views.index, name='index'),
    # path('index', views.index, name='index'),
    path('pay/<int:pk>/', views.pay, name='pay'),
    # path('operations', views.showOps, name='operations'),
    # path('submit_operation', views.submitOps, name='submit_operation'),
    path('api/config/', views.ConfigList.as_view()),
    path('api/config/<str:pk>/', views.ConfigGet.as_view()),
    path('api/config/update/<str:pk>/', views.ConfigUpdate.as_view()),
    path('api/log/add/', views.LogAdd.as_view()),
    path('api/user/get_by_date/<str:line>/<str:date>/<int:count>/', views.UserGetByDate.as_view()),
    path('api/user/update/<int:pk>/', views.UserUpdate.as_view()),
    path('api/user/get/<int:pk>/', views.UserGet.as_view()),
    path('api/user/slot/', views.UserGetSlot.as_view()),
    path('api/user/list/<str:status>/', views.UserGetByStatus.as_view()),
    path('api/user/get_schedule/<str:node>/', views.UserGetSchedule.as_view()),
    path('api/slot/list/', views.SlotGetList.as_view()),
    # batch create or update
    path('api/slot/', views.SlotUpdateViewSet.as_view({'post': 'create'})),
]
