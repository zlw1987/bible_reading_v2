"""Read-only generic Service Profile identity inventory command."""

import json

from django.core.management.base import BaseCommand

from events.service_profile_identity import (
    build_service_profile_identity_inventory,
)


def _display(value):
    return json.dumps(value, ensure_ascii=False)


def _datetime(value):
    return value.isoformat() if value is not None else "NULL"


class Command(BaseCommand):
    help = (
        "Read-only generic inventory of legacy ServiceEvent profile identities "
        "and ServiceProfile FK consistency. Writes nothing and has no --apply."
    )

    def handle(self, *args, **options):
        inventory = build_service_profile_identity_inventory()
        write = self.stdout.write
        write("Service Profile identity inventory (GENERIC-DEPLOYMENT-CONFIG.4A)")
        write("=" * 76)
        write("mode: read-only (no --apply exists; no data was changed)")
        write("ordering: legacy key, then event type; profiles by primary key")
        write("")
        write("legacy_key_type_groups:")
        for row in inventory["legacy_groups"]:
            write(
                f"  key={_display(row['legacy_key'])} | event_type={row['event_type']} "
                f"| events={row['total_event_count']} | fk_null={row['fk_null_count']} "
                f"| fk_nonnull={row['fk_nonnull_count']} "
                f"| exact_fk={row['exact_match_fk_count']} "
                f"| fk_mismatch={row['fk_mismatch_count']} "
                f"| fk_blank_key={row['fk_blank_key_count']} "
                f"| fk_key_mismatch={row['fk_key_mismatch_count']} "
                f"| event_profile_type_drift="
                f"{row['event_profile_type_mismatch_count']} "
                f"| earliest={_datetime(row['earliest_start_datetime'])} "
                f"| latest={_datetime(row['latest_start_datetime'])} "
                f"| statuses={_display(row['status_counts'])} "
                f"| referenced_profile_ids={_display(row['referenced_service_profile_ids'])} "
                f"| matching_profile_id={row['matching_service_profile_id'] or 'NULL'} "
                f"| key_integrity={row['legacy_key_integrity']} "
                f"| multi_type_conflict={str(row['multi_type_conflict']).lower()}"
            )

        blank = inventory["blank_legacy_key"]
        write("")
        write("blank_legacy_key_events:")
        write(
            f"  events={blank['total_event_count']} | fk_null={blank['fk_null_count']} "
            f"| fk_nonnull={blank['fk_nonnull_count']} "
            f"| fk_mismatch={blank['fk_mismatch_count']} "
            f"| fk_blank_key={blank['fk_blank_key_count']} "
            f"| fk_key_mismatch={blank['fk_key_mismatch_count']} "
            f"| event_profile_type_drift="
            f"{blank['event_profile_type_mismatch_count']} "
            f"| earliest={_datetime(blank['earliest_start_datetime'])} "
            f"| latest={_datetime(blank['latest_start_datetime'])} "
            f"| statuses={_display(blank['status_counts'])} "
            f"| referenced_profile_ids={_display(blank['referenced_service_profile_ids'])}"
        )

        write("")
        write("service_profiles:")
        for row in inventory["service_profiles"]:
            write(
                f"  pk={row['pk']} | key={_display(row['key'])} "
                f"| event_type={row['event_type']} | name={_display(row['name'])} "
                f"| name_en={_display(row['name_en'])} "
                f"| active={str(row['is_active']).lower()} "
                f"| linked_events={row['linked_service_event_count']} "
                f"| exact_links={row['exact_linked_event_count']} "
                f"| mismatched_links={row['mismatched_linked_event_count']} "
                f"| legacy_consistency={','.join(row['legacy_consistency_status'])}"
            )

        write("")
        write("integrity_blockers:")
        if inventory["integrity_blockers"]:
            for blocker in inventory["integrity_blockers"]:
                write(f"  - {blocker}")
        else:
            write("  none")

        write("")
        write("summary:")
        for key, value in inventory["summary"].items():
            write(f"  {key}: {value}")
        write(
            "READ-ONLY: no ServiceProfile or ServiceEvent row was created, "
            "updated, deleted, inferred, or repaired."
        )
