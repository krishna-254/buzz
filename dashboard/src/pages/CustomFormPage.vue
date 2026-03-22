<template>
	<BaseCustomEventForm :event-route="eventRoute" :form-route="formRoute" />
</template>

<script setup>
import BaseCustomEventForm from "@/components/BaseCustomEventForm.vue";

defineProps({
	eventRoute: { type: String, required: true },
	formRoute: { type: String, required: true },
});
</script>
