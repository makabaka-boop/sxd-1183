from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'specs', views.PaperSpecViewSet)
router.register(r'plates', views.PressPlateViewSet)
router.register(r'rules', views.ReviewRuleViewSet)
router.register(r'plans', views.BindingPlanViewSet)
router.register(r'batches', views.PaperBatchViewSet)
router.register(r'breaks', views.BreakRecordViewSet)
router.register(r'alerts', views.AnomalyAlertViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', views.StatsView.as_view(), name='stats'),
    path('stats/anomaly-rank/', views.anomaly_rank, name='anomaly-rank'),
    path('stats/pending-review/', views.pending_review_list, name='pending-review'),
    path('stats/press-duration/', views.press_duration_distribution, name='press-duration'),
    path('stats/plan-dashboard/', views.plan_dashboard_overview, name='plan-dashboard'),
    path('actions/run-detection/', views.run_anomaly_detection, name='run-detection'),
]
