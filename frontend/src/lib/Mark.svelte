<script lang="ts">
  let { size = 20 }: { size?: number } = $props();
</script>

<!-- A glint: what catches a magpie's eye. -->
<svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
  <path
    d="M10 1.5c.7 6.2 2.6 8.1 8.5 8.5-5.9.4-7.8 2.3-8.5 8.5-.7-6.2-2.6-8.1-8.5-8.5 5.9-.4 7.8-2.3 8.5-8.5Z"
    fill="currentColor"
  />
  <path
    d="M19 14c.3 2.9 1.2 3.8 4 4-2.8.2-3.7 1.1-4 4-.3-2.9-1.2-3.8-4-4 2.8-.2 3.7-1.1 4-4Z"
    fill="var(--sheen)"
  />
</svg>
