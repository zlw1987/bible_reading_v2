from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .visibility import member_visible_announcements_for


@login_required
def announcement_list(request):
    """List only currently published announcements visible to this member."""
    announcements = member_visible_announcements_for(request.user).order_by(
        "-publish_start",
        "-created_at",
        "-id",
    )
    return render(
        request,
        "announcements/announcement_list.html",
        {"announcements": announcements},
    )


@login_required
def announcement_detail(request, announcement_id):
    """Show one member-visible announcement or deny its existence with 404."""
    announcement = get_object_or_404(
        member_visible_announcements_for(request.user),
        id=announcement_id,
    )
    return render(
        request,
        "announcements/announcement_detail.html",
        {"announcement": announcement},
    )
