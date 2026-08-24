from django.urls import path

from .views import (
    CourseDetailView,
    CourseListCreateView,
    CourseManagementListView,
    CourseSessionDetailView,
    CourseSessionListCreateView,
    EnrollCourseView,
    MyEnrollmentListView,
    SessionProgressView,
    SessionQuizView,
    QuizAttemptCreateView,
    MyQuizAttemptListView,
    QuizManagementView,
    QuizManagementCreateView,
    SessionMediaTicketView,
    SessionMediaStreamView,
    CoursePurchaseView,
    CoursePurchaseStatusView,
)


urlpatterns = [
    path("sessions/<int:pk>/media-ticket/", SessionMediaTicketView.as_view(), name="academy-media-ticket"),
    path("sessions/<int:pk>/media/", SessionMediaStreamView.as_view(), name="academy-media-stream"),
    path("sessions/<int:pk>/quiz/", SessionQuizView.as_view(), name="academy-session-quiz"),
    path("quizzes/<int:pk>/attempts/", QuizAttemptCreateView.as_view(), name="academy-quiz-attempt"),
    path("quizzes/<int:pk>/attempts/mine/", MyQuizAttemptListView.as_view(), name="academy-my-quiz-attempts"),
    path("quizzes/manage/", QuizManagementCreateView.as_view(), name="academy-quiz-create"),
    path("quizzes/manage/<int:pk>/", QuizManagementView.as_view(), name="academy-quiz-detail"),
    path("enrollments/", MyEnrollmentListView.as_view(), name="academy-my-enrollments"),
    path("courses/<str:slug>/enroll/", EnrollCourseView.as_view(), name="academy-course-enroll"),
    path("courses/<str:slug>/purchase/", CoursePurchaseView.as_view(), name="academy-course-purchase"),
    path("courses/<str:slug>/purchase-status/", CoursePurchaseStatusView.as_view(), name="academy-course-purchase-status"),
    path("sessions/<int:pk>/progress/", SessionProgressView.as_view(), name="academy-session-progress"),
    path(
        "courses/manage/",
        CourseManagementListView.as_view(),
        name="academy-course-management",
    ),
    path(
        "courses/",
        CourseListCreateView.as_view(),
        name="academy-course-list-create",
    ),
    path(
        "courses/<str:slug>/sessions/",
        CourseSessionListCreateView.as_view(),
        name="academy-course-sessions",
    ),
    path(
        "courses/<str:slug>/",
        CourseDetailView.as_view(),
        name="academy-course-detail",
    ),
    path(
        "sessions/<int:pk>/",
        CourseSessionDetailView.as_view(),
        name="academy-session-detail",
    ),
]
