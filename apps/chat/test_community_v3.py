from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from rest_framework.test import APIClient

from apps.accounts.models import User
from .models import (
    ChatRoom, CommentReport, PollVote, PostComment, PostHashtag, PostUseful,
    RoomMembership, SocialAnalystProfile, TraderPost, UserFollow,
)
from apps.notifications.models import Notification


class CommunityV3Tests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="community-author", first_name="Sara")
        self.reader = User.objects.create_user(username="community-reader")
        self.other = User.objects.create_user(username="community-other")
        self.manager = User.objects.create_user(username="community-manager", role=User.Role.SUPER_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.author)

    def create_post(self, **fields):
        return self.client.post("/api/chat/social/feed/", {"text": "Market #ریسک update", "market": "crypto", **fields}, format="json")

    def test_market_required_and_legacy_general(self):
        bad = self.client.post("/api/chat/social/feed/", {"text": "No market"}, format="json")
        self.assertEqual(bad.status_code, 400)
        made = self.create_post()
        self.assertEqual(made.status_code, 201, made.data)
        self.assertEqual(made.data["market"], "crypto")
        old = TraderPost.objects.create(author=self.author, text="old")
        self.assertEqual(old.market, "general")
        self.assertEqual(self.client.patch(f"/api/chat/social/posts/{old.pk}/", {"text": "edited"}, format="json").status_code, 200)

    def test_feed_filters_hashtag_and_cursor(self):
        self.create_post(post_type="ANALYSIS")
        self.create_post(text="Other #ریسک #ریسک")
        self.create_post(text="Forex", market="forex")
        feed = self.client.get("/api/chat/social/feed/?market=crypto&hashtag=ریسک&page_size=1")
        self.assertEqual(feed.status_code, 200, feed.data)
        self.assertEqual(len(feed.data["results"]), 1)
        self.assertIsNotNone(feed.data["next"])
        self.assertEqual(PostHashtag.objects.filter(tag="ریسک").count(), 2)
        next_page = self.client.get(feed.data["next"])
        self.assertEqual(next_page.status_code, 200, next_page.data)
        self.assertNotEqual(feed.data["results"][0]["id"], next_page.data["results"][0]["id"])
        changed = self.client.get(feed.data["next"].replace("market=crypto", "market=forex"))
        self.assertEqual(changed.status_code, 400)
        analysis = self.client.get("/api/chat/social/feed/?feed=analysis")
        self.assertEqual(len(analysis.data["results"]), 1)

    def test_following_and_discussed_snapshot(self):
        followed = TraderPost.objects.create(author=self.author, text="first", market="general")
        other = TraderPost.objects.create(author=self.other, text="second", market="general")
        for index in range(2):
            PostComment.objects.create(post=followed, author=self.author, text=f"reply {index}")
        PostComment.objects.create(post=other, author=self.other, text="one")
        UserFollow.objects.create(follower=self.reader, following=self.author)
        self.client.force_authenticate(self.reader)
        following = self.client.get("/api/chat/social/feed/?feed=following")
        self.assertEqual([row["id"] for row in following.data["results"]], [followed.pk])
        first = self.client.get("/api/chat/social/feed/?feed=discussed&page_size=1")
        self.assertEqual(first.data["results"][0]["id"], followed.pk)
        for index in range(3):
            PostComment.objects.create(post=other, author=self.other, text=f"new {index}")
        second = self.client.get(first.data["next"])
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["results"][0]["id"], other.pk)

    def test_hashtag_edit_and_deleted_post_leave_no_trend(self):
        post_id = self.create_post(text="Old #طلا").data["id"]
        self.assertEqual(PostHashtag.objects.filter(post_id=post_id, tag="طلا").count(), 1)
        edited = self.client.patch(f"/api/chat/social/posts/{post_id}/", {"text": "New #بورس"}, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertFalse(PostHashtag.objects.filter(post_id=post_id, tag="طلا").exists())
        self.assertEqual(PostHashtag.objects.filter(post_id=post_id, tag="بورس").count(), 1)
        self.client.delete(f"/api/chat/social/posts/{post_id}/")
        self.assertNotIn("بورس", str(self.client.get("/api/chat/social/community/").data["trends"]))

    def test_invalid_multipart_poll_json_is_400(self):
        response = self.client.post("/api/chat/social/feed/", {"market": "general", "post_type": "POLL", "poll": "{broken"}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_private_content_not_in_feed_trends_or_profile(self):
        private = TraderPost.objects.create(author=self.author, text="private #سری", visibility="PRIVATE", market="crypto")
        PostHashtag.objects.create(post=private, tag="سری")
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(f"/api/chat/social/posts/{private.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/chat/social/users/{self.author.pk}/posts/").data["results"], [])
        self.assertNotIn("سری", str(self.client.get("/api/chat/social/community/").data["trends"]))

    def test_poll_vote_retry_and_wrong_option(self):
        made = self.create_post(text="", post_type="POLL", poll={"question": "Choose", "options": [{"text": "Yes"}, {"text": "No"}]})
        self.assertEqual(made.status_code, 201, made.data)
        post_id = made.data["id"]
        option_id = made.data["poll"]["options"][0]["id"]
        self.client.force_authenticate(self.reader)
        vote = self.client.post(f"/api/chat/social/posts/{post_id}/poll/vote/", {"option_id": option_id}, format="json")
        self.assertEqual(vote.status_code, 200, vote.data)
        self.assertEqual(vote.data["poll"]["total_votes"], 1)
        self.assertEqual(self.client.post(f"/api/chat/social/posts/{post_id}/poll/vote/", {"option_id": option_id}, format="json").status_code, 200)
        self.assertEqual(PollVote.objects.count(), 1)
        wrong = made.data["poll"]["options"][1]["id"]
        self.assertEqual(self.client.post(f"/api/chat/social/posts/{post_id}/poll/vote/", {"option_id": wrong}, format="json").status_code, 409)
        from .models import PostPoll
        PostPoll.objects.filter(post_id=post_id).update(closes_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f"/api/chat/social/posts/{post_id}/poll/vote/", {"option_id": option_id}, format="json").status_code, 409)

    def test_useful_and_report_comment_review(self):
        made = self.create_post()
        post_id = made.data["id"]
        self.client.force_authenticate(self.reader)
        for _ in range(2):
            self.assertEqual(self.client.post(f"/api/chat/social/posts/{post_id}/useful/", {}, format="json").status_code, 200)
        self.assertEqual(PostUseful.objects.count(), 1)
        comment = self.client.post(f"/api/chat/social/posts/{post_id}/comments/", {"text": "Useful"}, format="json")
        self.assertEqual(comment.status_code, 201, comment.data)
        cid = comment.data["id"]
        report = self.client.post(f"/api/chat/social/comments/{cid}/report/", {"reason": "ABUSE"}, format="json")
        self.assertEqual(report.status_code, 201)
        self.client.force_authenticate(self.manager)
        queue = self.client.get("/api/chat/social/manage/reports/?status=PENDING")
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.data["count"], 1)
        review = self.client.patch(f"/api/chat/social/manage/reports/{queue.data['results'][0]['id']}/", {"action": "REMOVE_CONTENT"}, format="json")
        self.assertEqual(review.status_code, 200, review.data)
        self.assertTrue(PostComment.objects.get(pk=cid).is_deleted)
        self.assertEqual(CommentReport.objects.get(pk=report.data["id"]).status, "RESOLVED")

    def test_analyst_manage_and_self_update_forbidden(self):
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.patch(f"/api/chat/social/manage/analysts/{self.reader.pk}/", {"is_verified": True}, format="json").status_code, 403)
        self.client.force_authenticate(self.manager)
        updated = self.client.patch(f"/api/chat/social/manage/analysts/{self.reader.pk}/", {"is_verified": True, "is_active_analyst": True, "credibility_score": 94}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertTrue(SocialAnalystProfile.objects.get(user=self.reader).is_verified)
        self.client.force_authenticate(self.author)
        listed = self.client.get("/api/chat/social/analysts/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["results"][0]["id"], self.reader.pk)

    def test_private_room_invitation_requires_acceptance(self):
        room = ChatRoom.objects.create(name="Secret V3", is_public=False, created_by=self.manager)
        RoomMembership.objects.create(room=room, user=self.manager, role=RoomMembership.Role.ADMIN)
        self.client.force_authenticate(self.manager)
        invitation = self.client.post(f"/api/chat/{room.slug}/invitations/", {"user_id": self.reader.pk}, format="json")
        self.assertEqual(invitation.status_code, 201, invitation.data)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(f"/api/chat/{room.slug}/messages/").status_code, 403)
        accepted = self.client.post(f"/api/chat/invitations/{invitation.data['id']}/accept/", {}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(self.client.post(f"/api/chat/invitations/{invitation.data['id']}/accept/", {}, format="json").status_code, 200)
        self.assertEqual(self.client.get(f"/api/chat/{room.slug}/messages/").status_code, 200)

    def test_social_notifications_are_generic_and_idempotent(self):
        post_id = self.create_post().data["id"]
        self.client.force_authenticate(self.reader)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/chat/social/posts/{post_id}/reaction/", {"reaction_type": "LIKE"}, format="json")
            self.client.post(f"/api/chat/social/posts/{post_id}/reaction/", {"reaction_type": "LIKE"}, format="json")
            self.client.post(f"/api/chat/social/posts/{post_id}/comments/", {"text": "Comment"}, format="json")
            self.client.post(f"/api/chat/social/users/{self.author.pk}/follow/", {}, format="json")
            self.client.post(f"/api/chat/social/users/{self.author.pk}/follow/", {}, format="json")
        rows = Notification.objects.filter(recipient=self.author, notification_type=Notification.Type.SOCIAL)
        self.assertEqual(rows.count(), 3)
        self.assertFalse(rows.filter(send_sms=True).exists())
        self.assertNotIn("Market #ریسک update", str(list(rows.values_list("message", flat=True))))

    def test_room_presence_counts_one_user_once_and_clears_on_leave(self):
        class FakeRedis:
            def __init__(self):
                self.values = {}
            def zadd(self, key, values):
                self.values.setdefault(key, {}).update(values)
            def zrangebyscore(self, key, minimum, maximum):
                now = float(minimum)
                return [member.encode() for member, expiry in self.values.get(key, {}).items() if expiry >= now]
            def zremrangebyscore(self, key, minimum, maximum):
                now = float(maximum)
                self.values[key] = {member: expiry for member, expiry in self.values.get(key, {}).items() if expiry > now}
            def zrem(self, key, member):
                self.values.get(key, {}).pop(member, None)
            def expire(self, key, ttl):
                return True
            def ping(self):
                return True
        room = ChatRoom.objects.create(name="Presence V3", created_by=self.manager)
        RoomMembership.objects.create(room=room, user=self.reader)
        self.client.force_authenticate(self.reader)
        fake = FakeRedis()
        with patch("apps.chat.community._redis", return_value=fake):
            path = f"/api/chat/{room.slug}/presence/"
            self.assertEqual(self.client.post(path, {}, format="json").data["online_count"], 1)
            self.assertEqual(self.client.post(path, {}, format="json").data["online_count"], 1)
            self.assertEqual(self.client.post(f"/api/chat/{room.slug}/leave/", {}, format="json").status_code, 200)
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 403)

    def test_comment_owner_and_manager_only(self):
        post_id = self.create_post().data["id"]
        self.client.force_authenticate(self.reader)
        comment_id = self.client.post(f"/api/chat/social/posts/{post_id}/comments/", {"text": "mine"}, format="json").data["id"]
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.patch(f"/api/chat/social/comments/{comment_id}/", {"text": "changed"}, format="json").status_code, 403)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.patch(f"/api/chat/social/comments/{comment_id}/", {"text": "changed"}, format="json").status_code, 200)

    def test_feed_query_count_is_bounded_for_many_authors(self):
        for index in range(12):
            author = User.objects.create_user(username=f"feed-writer-{index}", first_name=f"Writer {index}")
            TraderPost.objects.create(author=author, market="general", text=f"post {index}")
        self.client.force_authenticate(self.reader)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/chat/social/feed/?page_size=20")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 12)
        self.assertLessEqual(len(queries), 20, f"Feed used {len(queries)} queries for 12 authors")

    def test_poll_feed_query_count_is_bounded(self):
        from .models import PollOption, PostPoll
        for index in range(8):
            post = TraderPost.objects.create(author=self.author, market="general", post_type="POLL")
            poll = PostPoll.objects.create(post=post, question=f"Question {index}")
            PollOption.objects.create(poll=poll, text="Yes", position=0)
            PollOption.objects.create(poll=poll, text="No", position=1)
        self.client.force_authenticate(self.reader)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/chat/social/feed/?page_size=20")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 8)
        self.assertLessEqual(len(queries), 20, f"Poll feed used {len(queries)} queries")
