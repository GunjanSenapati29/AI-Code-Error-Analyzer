# from django.urls import path
# from . import views

# urlpatterns = [
#     path('', views.index, name='index'),
#     path('api/auth/login/', views.login_view),
#     path('api/auth/signup/', views.signup_view),
#     path('api/auth/logout/', views.logout_view),
#     path('api/session/', views.session_view),
#     path('api/dashboard/', views.dashboard_api),
#     path('api/history/', views.history_api),
#     path('api/history/clear/', views.clear_history_api),
#     path('api/history/<int:record_id>/', views.history_detail_api),
#     path('api/chat/mentor/', views.mentor_chat_api),
#     path('api/ai/status/', views.ai_status_api),
#     path('api/report/<int:record_id>/txt/', views.report_txt),
#     path('api/report/<int:record_id>/pdf/', views.report_pdf),
# ]


from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/auth/login/', views.login_view),
    path('api/auth/signup/', views.signup_view),
    path('api/auth/logout/', views.logout_view),
    path('api/session/', views.session_view),
    path('api/dashboard/', views.dashboard_api),
    path('api/history/', views.history_api),
    path('api/history/clear/', views.clear_history_api),
    path('api/history/<int:record_id>/', views.history_detail_api),
    path('api/chat/mentor/', views.mentor_chat_api),
    path('api/ai/status/', views.ai_status_api),
    path('api/report/<int:record_id>/txt/', views.report_txt),
    path('api/report/<int:record_id>/pdf/', views.report_pdf),
]