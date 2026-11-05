<script lang="ts">
  import type { Candidate } from './types';

  let { piece }: { piece: Candidate } = $props();

  const maker = $derived(piece.artist || piece.culture || 'Unknown maker');
  const bio = $derived(piece.artist ? piece.artist_bio : piece.period);
  const source = $derived(piece.source === 'wikidata' ? 'See it on Wikidata' : 'See it at the Met');
</script>

<!-- The tombstone label a museum hangs beside a piece. -->
<div class="label">
  <p class="maker">{maker}</p>
  {#if bio}<p class="bio">{bio}</p>{/if}
  <p class="title"><cite>{piece.title}</cite>{#if piece.date}, {piece.date}{/if}</p>
  {#if piece.medium}<p class="medium">{piece.medium}</p>{/if}
  {#if piece.dimensions}<p class="small">{piece.dimensions.split('\n')[0]}</p>{/if}
  {#if piece.source === 'wikidata'}
    {#if piece.credit_line}<p class="small soft">{piece.credit_line}</p>{/if}
  {:else}
    <p class="small soft">{piece.department}</p>
  {/if}
  {#if piece.museum_url}
    <a class="source" href={piece.museum_url} target="_blank" rel="noreferrer">{source}</a>
  {/if}
</div>

<style>
  .label {
    background: var(--paper);
    color: var(--ink);
    font-family: var(--serif);
    font-size: 14px;
    line-height: 1.5;
    padding: 16px 18px 14px;
    border-radius: 2px;
    box-shadow: 0 6px 18px rgb(0 0 0 / 0.22);
    width: 100%;
  }

  p {
    margin: 0;
  }

  .maker {
    font-weight: 620;
    font-size: 15px;
  }

  .bio {
    color: var(--ink-soft);
    font-size: 12.5px;
    margin-bottom: 10px;
  }

  .title {
    font-size: 16px;
    line-height: 1.35;
    margin-bottom: 8px;
    text-wrap: balance;
  }

  cite {
    font-style: italic;
  }

  .medium {
    margin-bottom: 2px;
  }

  .small {
    font-size: 12.5px;
  }

  .soft {
    color: var(--ink-soft);
    margin-top: 8px;
  }

  .source {
    display: inline-block;
    margin-top: 10px;
    font-family: var(--sans);
    font-size: 13px;
    color: var(--ink);
    text-underline-offset: 3px;
  }
</style>
