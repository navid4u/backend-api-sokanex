from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from apps.academy.models import Course, CourseSession


class AcademyAndCustomRoleAPITests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="academy-admin",
            password=self.password,
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="teacher",
            password=self.password,
        )
        self.other_teacher = User.objects.create_user(
            username="other-teacher",
            password=self.password,
        )
        self.level_one = User.objects.create_user(
            username="level-one",
            password=self.password,
            access_level=1,
        )
        self.level_two = User.objects.create_user(
            username="level-two",
            password=self.password,
            access_level=2,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_teacher_role(self):
        return PlatformRole.objects.create(
            name="Instructor",
            slug="instructor",
            permissions=[User.Permission.ACADEMY_TEACH],
            created_by=self.admin,
        )

    def test_registration_creates_level_one_user(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "registered-user",
                "email": "registered@example.com",
                "password": self.password,
                "first_name": "New",
                "last_name": "User",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="registered-user")
        self.assertEqual(user.role, User.Role.USER)
        self.assertEqual(user.access_level, 1)

    def test_admin_can_create_and_assign_teacher_role(self):
        self.authenticate(self.admin)
        role_response = self.client.post(
            reverse("platform-role-list-create"),
            {
                "name": "Academy Teacher",
                "permissions": [User.Permission.ACADEMY_TEACH],
            },
            format="json",
        )
        self.assertEqual(
            role_response.status_code,
            status.HTTP_201_CREATED,
        )
        role_id = role_response.data["id"]

        assign_response = self.client.patch(
            reverse(
                "user-custom-role-update",
                kwargs={"pk": self.teacher.pk},
            ),
            {"custom_role_id": role_id},
            format="json",
        )
        self.assertEqual(
            assign_response.status_code,
            status.HTTP_200_OK,
        )
        self.teacher.refresh_from_db()
        self.assertTrue(
            self.teacher.has_platform_permission(
                User.Permission.ACADEMY_TEACH
            )
        )

    def test_teacher_can_create_course_and_sessions(self):
        role = self.create_teacher_role()
        self.teacher.custom_role = role
        self.teacher.save(update_fields=["custom_role"])
        self.authenticate(self.teacher)

        course_response = self.client.post(
            reverse("academy-course-list-create"),
            {
                "title": "Trading foundations",
                "description": "A structured course",
                "status": Course.Status.PUBLISHED,
                "allowed_levels": [2, 3],
            },
            format="json",
        )
        self.assertEqual(
            course_response.status_code,
            status.HTTP_201_CREATED,
        )
        course = Course.objects.get()
        self.assertEqual(course.instructor, self.teacher)
        self.assertEqual(course.allowed_levels, [2, 3])

        session_response = self.client.post(
            reverse(
                "academy-course-sessions",
                kwargs={"slug": course.slug},
            ),
            {
                "title": "Session one",
                "order": 1,
                "video_url": "https://example.com/video",
                "text": "Lesson notes",
            },
            format="json",
        )
        self.assertEqual(
            session_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(CourseSession.objects.count(), 1)

    def test_course_visibility_is_restricted_by_level(self):
        Course.objects.create(
            title="Level two course",
            instructor=self.admin,
            status=Course.Status.PUBLISHED,
            allowed_level_1=False,
            allowed_level_2=True,
            allowed_level_3=False,
            allowed_level_4=False,
            allowed_level_5=False,
        )

        self.authenticate(self.level_one)
        hidden_response = self.client.get(
            reverse("academy-course-list-create")
        )
        self.assertEqual(hidden_response.data["count"], 0)

        self.authenticate(self.level_two)
        visible_response = self.client.get(
            reverse("academy-course-list-create")
        )
        self.assertEqual(visible_response.data["count"], 1)

    def test_teacher_cannot_edit_another_teachers_course(self):
        role = self.create_teacher_role()
        self.teacher.custom_role = role
        self.other_teacher.custom_role = role
        self.teacher.save(update_fields=["custom_role"])
        self.other_teacher.save(update_fields=["custom_role"])
        course = Course.objects.create(
            title="Owned course",
            instructor=self.teacher,
        )

        self.authenticate(self.other_teacher)
        response = self.client.patch(
            reverse(
                "academy-course-detail",
                kwargs={"slug": course.slug},
            ),
            {"title": "Unauthorized edit"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_edit_any_course(self):
        course = Course.objects.create(
            title="Teacher course",
            instructor=self.teacher,
        )
        self.authenticate(self.admin)
        response = self.client.patch(
            reverse(
                "academy-course-detail",
                kwargs={"slug": course.slug},
            ),
            {"title": "Admin edited"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        course.refresh_from_db()
        self.assertEqual(course.title, "Admin edited")

    def test_course_returns_instructor_real_name(self):
        self.teacher.first_name = "Ali"
        self.teacher.last_name = "Karimi"
        self.teacher.save(
            update_fields=["first_name", "last_name"]
        )
        Course.objects.create(
            title="Named instructor course",
            instructor=self.teacher,
            status=Course.Status.PUBLISHED,
        )
        self.authenticate(self.level_one)
        response = self.client.get(
            reverse("academy-course-list-create")
        )
        course = response.data["results"][0]
        self.assertEqual(course["instructor"], self.teacher.username)
        self.assertEqual(course["instructor_name"], "Ali Karimi")
