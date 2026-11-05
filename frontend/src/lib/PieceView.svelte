<script lang="ts">
  import { app } from './app.svelte';
  import Label from './Label.svelte';
  import { FACETS, FACET_NAMES, type Facet, type Kept } from './types';

  let { piece }: { piece: Kept } = $props();

  let confirming = $state(false);

  function browse(facet: Facet, value: string) {
    app.filters = [{ facet, value }];
    location.hash = '#/hoard';
  }

  function letGo() {
    app.letGo(piece);
    location.hash = '#/hoard';
  }

  const failed = $derived(piece.tag_status === 'failed' || piece.image_status === 'failed');
</script>

<article class="piece" aria-label={piece.title}>
  <a class="back" href="#/hoard">Back to the hoard</a>

  <figure class="hang">
    <img src={piece.image} alt={piece.title} width={piece.width} height={piece.height} />
    <figcaption><Label {piece} /></figcaption>
  </figure>

  <div class="about">
    {#if piece.unsent}
      <p class="status">Kept on this device. Tags arrive once the Pi has it.</p>
    {:else if failed}
      <p class="status">{piece.tag_error ?? "This piece couldn't be tagged."}</p>
      <button class="quiet" onclick={() => app.retry(piece)}>Try tagging again</button>
    {:else if piece.tag_status === 'pending'}
      <p class="status">Claude is looking at this one. Tags will appear in a moment.</p>
    {:else}
      {#if piece.note}
        <section class="note">
          <h2>Notes for sketching</h2>
          <p>{piece.note}</p>
        </section>
      {/if}
      <dl class="tags">
        {#each FACETS as facet}
          {#if piece.tags[facet]?.length}
            <div>
              <dt>{FACET_NAMES[facet]}</dt>
              <dd>
                {#each piece.tags[facet] as value}
                  <button onclick={() => browse(facet, value)}>{value}</button>
                {/each}
              </dd>
            </div>
          {/if}
        {/each}
      </dl>
    {/if}

    <div class="letgo">
      {#if confirming}
        <span>Let go of this piece? It won't be offered again.</span>
        <button class="quiet" onclick={letGo}>Let it go</button>
        <button class="link" onclick={() => (confirming = false)}>Keep it</button>
      {:else}
        <button class="link" onclick={() => (confirming = true)}>Let go…</button>
      {/if}
    </div>
  </div>
</article>

<style>
  .piece {
    padding: 4px var(--gutter) 64px;
    max-width: 1300px;
    margin: 0 auto;
  }

  .back {
    font-size: 15px;
    color: var(--on-wall-soft);
    text-underline-offset: 3px;
  }

  .hang {
    margin: 20px 0 0;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    gap: 32px;
  }

  img {
    display: block;
    min-width: 0;
    max-width: calc(100vw - 2 * var(--gutter) - 248px - 32px);
    max-height: calc(100dvh - 160px);
    width: auto;
    height: auto;
    box-shadow: 0 24px 48px -12px rgb(0 0 0 / 0.55);
  }

  figcaption {
    flex: none;
    width: 248px;
  }

  .about {
    max-width: 680px;
    margin: 48px auto 0;
  }

  .status {
    font-family: var(--serif);
    font-style: italic;
    font-size: 17px;
    color: var(--on-wall-soft);
    margin: 0 0 12px;
  }

  h2 {
    font-family: var(--serif);
    font-weight: 500;
    font-size: 20px;
    margin: 0 0 8px;
  }

  .note p {
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.65;
    margin: 0;
    max-width: 62ch;
  }

  .tags {
    margin: 32px 0 0;
    display: grid;
    gap: 14px;
  }

  .tags div {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 12px;
    align-items: baseline;
  }

  dt {
    color: var(--on-wall-soft);
    font-size: 14px;
  }

  dd {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  dd button {
    background: transparent;
    border: 1px solid var(--on-wall-faint);
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 14px;
  }

  dd button:hover {
    background: rgb(255 255 255 / 0.08);
  }

  .letgo {
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid var(--on-wall-faint);
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    font-size: 14.5px;
    color: var(--on-wall-soft);
  }

  .quiet {
    background: var(--paper);
    color: var(--ink);
    border: 0;
    border-radius: 999px;
    padding: 7px 16px;
    font-size: 14.5px;
  }

  .link {
    background: none;
    border: 0;
    padding: 0;
    color: var(--on-wall-soft);
    text-decoration: underline;
    text-underline-offset: 3px;
    font-size: 14.5px;
  }

  @media (max-width: 760px) {
    .hang {
      flex-direction: column;
      align-items: center;
      gap: 16px;
    }

    img {
      max-height: 62dvh;
      max-width: calc(100vw - 2 * var(--gutter));
    }

    figcaption {
      width: min(100%, 420px);
    }

    .tags div {
      grid-template-columns: 1fr;
      gap: 4px;
    }
  }
</style>
