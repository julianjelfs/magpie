<script lang="ts">
  import { app } from './app.svelte';
  import { counts, leaning, matches } from './hoard';
  import { FACETS, FACET_NAMES, type Facet } from './types';

  let facet = $state<Facet>('movement');

  const pieces = $derived(app.hoard);
  const shown = $derived(pieces.filter((p) => matches(p, app.filters)));
  const values = $derived(counts(shown, facet).filter((c) => !app.filters.some((f) => f.facet === facet && f.value === c.value)));
  const sentence = $derived(leaning(pieces));

  function add(value: string) {
    app.filters = [...app.filters, { facet, value }];
  }

  function remove(i: number) {
    app.filters = app.filters.filter((_, j) => j !== i);
  }

  function asOf(iso: string | null) {
    if (!iso) return 'an earlier visit';
    const d = new Date(iso);
    const today = new Date().toDateString() === d.toDateString();
    return today
      ? d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' });
  }
</script>

<section class="hoard" aria-labelledby="hoard-title">
  <header>
    <h1 id="hoard-title">Hoard</h1>
    <p class="count">
      {pieces.length === 1 ? 'One piece' : `${pieces.length} pieces`}{#if sentence}. {sentence}{/if}
      <a class="taste-link" href="#/taste">What you keep</a>
    </p>
    {#if !app.reachable}
      <p class="offline">
        The Pi is out of reach, so this is your hoard as of {asOf(app.hoardAsOf)}.
        {#if app.unsent}Changes made since will be sent when it's back.{/if}
      </p>
    {/if}
  </header>

  {#if pieces.length === 0}
    <div class="empty">
      <p>Nothing kept yet. Every piece you keep lands here, tagged by period, movement, medium and more.</p>
      <a href="#/">Start looking</a>
    </div>
  {:else}
    <div class="filters">
      <div class="facets" role="tablist" aria-label="Browse by">
        {#each FACETS as f}
          <button role="tab" aria-selected={facet === f} class:on={facet === f} onclick={() => (facet = f)}>
            {FACET_NAMES[f]}
          </button>
        {/each}
      </div>

      {#if app.filters.length}
        <div class="chosen">
          {#each app.filters as f, i}
            <button class="pill" onclick={() => remove(i)} aria-label={`Remove ${f.value}`}>
              {f.value} <span aria-hidden="true">×</span>
            </button>
          {/each}
          <button class="clear" onclick={() => (app.filters = [])}>Clear</button>
        </div>
      {/if}

      <div class="values">
        {#each values as v}
          <button class="value" onclick={() => add(v.value)}>
            {v.value} <span class="n">{v.count}</span>
          </button>
        {:else}
          <p class="none">No {FACET_NAMES[facet].toLowerCase()} tags among these yet.</p>
        {/each}
      </div>
    </div>

    {#if shown.length === 0}
      <p class="none">Nothing matches all of those. Remove a filter to see more.</p>
    {/if}

    <ul class="salon">
      {#each shown as p (p.key)}
        <li>
          <a href={`#/hoard/${p.key}`} aria-label={`${p.title}${p.artist ? `, ${p.artist}` : ''}`}>
            <img src={p.thumb} alt="" width={p.width} height={p.height} loading="lazy" style:background={p.wall_colour} />
            <span class="caption">
              <span class="who">{p.artist || p.culture || 'Unknown maker'}</span>
              <cite>{p.title}</cite>
            </span>
            {#if p.unsent}
              <span class="state">Not sent yet</span>
            {:else if p.tag_status === 'failed' || p.image_status === 'failed'}
              <span class="state">Couldn't tag</span>
            {:else if p.tag_status === 'pending'}
              <span class="state">Tagging…</span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .hoard {
    padding: 8px var(--gutter) 64px;
    max-width: 1500px;
    margin: 0 auto;
  }

  h1 {
    font-family: var(--serif);
    font-weight: 400;
    font-size: clamp(40px, 6vw, 64px);
    line-height: 1;
    letter-spacing: -0.01em;
    margin: 12px 0 10px;
  }

  .count {
    margin: 0;
    color: var(--on-wall-soft);
    font-size: 16px;
    max-width: 60ch;
  }

  .taste-link {
    margin-left: 12px;
    color: var(--on-wall);
    text-underline-offset: 3px;
    white-space: nowrap;
  }

  .offline {
    margin: 12px 0 0;
    padding: 10px 14px;
    border-left: 2px solid var(--sheen);
    background: rgb(255 255 255 / 0.05);
    max-width: 62ch;
    font-size: 14.5px;
  }

  .empty {
    margin-top: 48px;
    max-width: 44ch;
    font-family: var(--serif);
    font-size: 19px;
    color: var(--on-wall-soft);
  }

  .empty a {
    font-family: var(--sans);
    font-size: 15px;
    color: var(--on-wall);
  }

  .filters {
    margin: 28px 0 24px;
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--wall);
    padding: 8px 0 12px;
    transition: background-color var(--wall-change) ease;
  }

  .facets {
    display: flex;
    gap: 22px;
    overflow-x: auto;
    border-bottom: 1px solid var(--on-wall-faint);
    scrollbar-width: none;
  }

  .facets button {
    background: none;
    border: 0;
    padding: 8px 0 10px;
    color: var(--on-wall-soft);
    font-size: 15px;
    white-space: nowrap;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }

  .facets button.on {
    color: var(--on-wall);
    border-bottom-color: var(--on-wall);
  }

  .chosen,
  .values {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  .values {
    max-height: 96px;
    overflow-y: auto;
  }

  .value,
  .pill,
  .clear {
    border-radius: 999px;
    padding: 5px 12px;
    font-size: 14px;
  }

  .value {
    background: transparent;
    border: 1px solid var(--on-wall-faint);
  }

  .value:hover {
    background: rgb(255 255 255 / 0.08);
  }

  .n {
    color: var(--on-wall-soft);
    font-variant-numeric: tabular-nums;
    margin-left: 4px;
  }

  .pill {
    background: var(--paper);
    color: var(--ink);
    border: 1px solid var(--paper);
  }

  .clear {
    background: none;
    border: 0;
    color: var(--on-wall-soft);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .none {
    color: var(--on-wall-soft);
    font-size: 14.5px;
    margin: 4px 0;
  }

  /* A salon hang: pictures close together, each at its own shape. */
  .salon {
    list-style: none;
    margin: 0;
    padding: 0;
    columns: 4 220px;
    column-gap: 22px;
  }

  .salon li {
    break-inside: avoid;
    margin-bottom: 26px;
  }

  .salon a {
    display: block;
    text-decoration: none;
    position: relative;
  }

  .salon img {
    display: block;
    width: 100%;
    height: auto;
    box-shadow: 0 12px 24px -10px rgb(0 0 0 / 0.6);
    transition: transform 200ms ease;
  }

  .salon a:hover img {
    transform: translateY(-2px);
  }

  .caption {
    display: block;
    margin-top: 9px;
    font-size: 13.5px;
    line-height: 1.35;
  }

  .who {
    display: block;
    color: var(--on-wall-soft);
  }

  cite {
    display: block;
    font-family: var(--serif);
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 520px) {
    .salon {
      columns: 2;
      column-gap: 14px;
    }

    .salon li {
      margin-bottom: 18px;
    }
  }

  .state {
    position: absolute;
    top: 8px;
    left: 8px;
    background: var(--paper);
    color: var(--ink);
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 2px;
  }
</style>
