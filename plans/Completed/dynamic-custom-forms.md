# Plan: Dynamic Custom Forms via Child Table

## Context

Currently, custom forms are hardcoded to 3 types (Event Feedback, Talk Proposal, Sponsorship Enquiry) via `CUSTOM_FORM_CONFIG` dict in `buzz/api.py`. Each form type requires a toggle field, deadline field, success message field on Buzz Event, a hardcoded config entry, and a dedicated Vue wrapper page + route. This doesn't scale. We want users to attach **any DocType** as a publishable form on their event via a child table.

**Decision:** Migrate all 3 existing forms into the child table system (no dual system). Allow any DocType — no validation on event/additional_fields fields existing.

---

## Changes

### 1. New Child Table DocType: `Buzz Event Form`

**New directory:** `buzz/events/doctype/buzz_event_form/`

| Field | Type | Notes |
|-------|------|-------|
| `form_doctype` | Link (DocType) | Which DocType to render as a form |
| `publish` | Check | Whether the form is live |
| `auto_close_at` | Datetime | Auto-close submissions after this time |
| `route` | Data, reqd, in_list_view | URL slug (e.g. `feedback`, `propose-talk`) |
| `success_message` | Markdown Editor | Shown after successful submission |

- `istable: 1`, parent is Buzz Event
- Controller validates `route` uniqueness within the event

### 2. Update Buzz Event DocType

**File:** `buzz/events/doctype/buzz_event/buzz_event.json`

- Add `custom_forms` child table field (Table → Buzz Event Form) in the Forms section
- **Remove** the now-redundant fields:
  - `accept_event_feedback`, `accept_talk_proposals`, `accept_sponsorship_enquiries` (toggle checks)
  - `talk_proposals_close_at`, `sponsorship_proposals_close_at` (deadlines — `registrations_close_at` stays, it's for ticketing)
  - `feedback_success_message`, `proposal_success_message`, `sponsorship_success_message` (success messages)
- Keep `auto_closures_section` and `registrations_close_at` (those are for ticket registration, not forms)

### 3. Update Buzz Custom Field `applied_to`

**File:** `buzz/buzz/doctype/buzz_custom_field/buzz_custom_field.json`

- Add `Custom Form` option to `applied_to` Select:
  `"Booking\nTicket\nOffline Payment Form\nCustom Form"`
- Remove the 3 hardcoded options: `Event Feedback`, `Talk Proposal`, `Sponsorship Enquiry`
- Add new field `custom_form_doctype` (Link → DocType):
  - `depends_on`: `eval:doc.applied_to === 'Custom Form'`
  - `mandatory_depends_on`: `eval:doc.applied_to === 'Custom Form'`
  - Label: "Custom Form DocType"
- When filtering custom fields in the API, match on `applied_to == "Custom Form"` AND `custom_form_doctype == <the form's DocType>`

### 4. Backend API Changes

**File:** `buzz/api.py`

**4a. Replace `CUSTOM_FORM_CONFIG` with a universal `STANDARD_EXCLUDE_FIELDS` set.**

```python
STANDARD_EXCLUDE_FIELDS = {
    "name", "owner", "creation", "modified", "modified_by",
    "docstatus", "idx", "additional_fields", "event",
    "section_break_additional",
}
```

This covers meta/internal fields that should never appear on a public form. `get_form_fields` already handles hidden, read-only, and layout fields. Per-form config (deadline, success message, route, enabled) now comes from the child table row.

**4b. Update `validate_custom_form(event_route, form_route)`**
- Change signature: accept `form_route` (the slug) instead of `form_type` (DocType name)
- Look up event by route, then find matching row in `event_doc.custom_forms` where `route == form_route` and `publish == 1`
- Check event is published
- Return the matched child table row + event_doc

**4c. Update `get_custom_form_data(event_route, form_route)`**
- Get the child row via validate
- `form_type` = `row.form_doctype` (the DocType name)
- Build exclude_fields dynamically: standard meta fields (`name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx`) + `additional_fields` + `event` + any Section/Column break containing `additional`
- Deadline: check `row.auto_close_at` directly
- Custom fields: filter `Buzz Custom Field` where `applied_to == "Custom Form"` AND `custom_form_doctype == form_type` AND `event == event_doc.name` AND `enabled == 1`
- Success message: from `row.success_message`
- Auto-set: if DocType has an `event` field → auto-set from route; if it has `submitted_by` → auto-set from session user

**4d. Update `submit_custom_form(event_route, form_route, data, custom_fields_data)`**
- Same flow but config comes from child table row
- DocType to create = `row.form_doctype`
- Auto-detect `event` and `submitted_by` fields from DocType meta

**4e. New API: `get_event_forms(event_route)`**
- Returns list of published forms: `[{route, doctype, label (from DocType meta)}]`
- Useful for frontend to build navigation/links to available forms

**4f. Update `get_form_fields`**
- Make the exclude set a parameter with sensible defaults (the standard fields)

### 5. Frontend Changes

**File:** `dashboard/src/router.ts`

- Remove the 3 hardcoded form routes (`/events/:eventRoute/feedback`, etc.)
- Add single dynamic route: `/events/:eventRoute/forms/:formRoute` → `CustomFormPage.vue`
  - `meta: { isPublic: true }`, `props: true`

**New file:** `dashboard/src/pages/CustomFormPage.vue`
- Props: `eventRoute`, `formRoute`
- Calls `get_custom_form_data(event_route, form_route)` — the API now accepts route slug
- Derives title from DocType label (returned by API)
- Passes to `BaseCustomEventForm` (which needs minor update to accept `formRoute` instead of `formType`)

**File:** `dashboard/src/components/BaseCustomEventForm.vue`
- Update props: accept `formRoute` (route slug) instead of `formType` (DocType name)
- Update resource calls to pass `form_route` instead of `form_type`
- Everything else stays the same — it already renders fields generically

**Delete:**
- `dashboard/src/pages/FeedbackForm.vue`
- `dashboard/src/pages/ProposeTalkForm.vue`
- `dashboard/src/pages/EnquireSponsorshipForm.vue`

---

## Files Summary

| File | Action | Change |
|------|--------|--------|
| `buzz/events/doctype/buzz_event_form/` | **New** | Child table DocType (4 files) |
| `buzz/events/doctype/buzz_event/buzz_event.json` | Modify | Add `custom_forms` table, remove 8 form-related fields |
| `buzz/buzz/doctype/buzz_custom_field/buzz_custom_field.json` | Modify | Replace 3 hardcoded options with "Custom Form" + add `custom_form_doctype` Link |
| `buzz/api.py` | Modify | Remove CUSTOM_FORM_CONFIG, rewrite validate/get/submit to use child table, add `get_event_forms` |
| `dashboard/src/router.ts` | Modify | Replace 3 routes with 1 dynamic route |
| `dashboard/src/pages/CustomFormPage.vue` | **New** | Single dynamic form wrapper |
| `dashboard/src/components/BaseCustomEventForm.vue` | Modify | Accept `formRoute` instead of `formType` |
| `dashboard/src/pages/FeedbackForm.vue` | **Delete** | No longer needed |
| `dashboard/src/pages/ProposeTalkForm.vue` | **Delete** | No longer needed |
| `dashboard/src/pages/EnquireSponsorshipForm.vue` | **Delete** | No longer needed |

## Implementation Order

1. Create `Buzz Event Form` child table DocType
2. Update Buzz Event DocType (add child table, remove old fields) + `bench migrate`
3. Update Buzz Custom Field (new option + link field) + `bench migrate`
4. Rewrite `buzz/api.py` — remove hardcoded config, dynamic resolution from child table
5. Frontend: new route + `CustomFormPage.vue` + update `BaseCustomEventForm.vue` + delete old wrappers
6. Test end-to-end

## Verification

1. On a Buzz Event, add "Event Feedback" to `custom_forms` with route=`feedback`, publish=1
2. Add "Talk Proposal" with route=`propose-talk`, publish=1, auto_close_at=future
3. Navigate to `/dashboard/events/{eventRoute}/forms/feedback` — verify form renders
4. Submit feedback → verify doc created with correct event link
5. Add Buzz Custom Fields with `applied_to="Custom Form"`, `custom_form_doctype="Event Feedback"` → verify they appear on the form
6. Set `auto_close_at` to past → verify form shows closed message
7. Create a brand new DocType, add it to custom_forms → verify it works as a form
8. Unpublish a form → verify 404
