from django.contrib import admin
from .models import Channel, ChannelMembership, ChannelPost

admin.site.register(Channel)
admin.site.register(ChannelMembership)
admin.site.register(ChannelPost)
