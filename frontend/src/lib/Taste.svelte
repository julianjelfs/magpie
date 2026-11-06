<script lang="ts">
  import { Unreachable, fetchTaste, type Group, type Taste } from './api';

  let taste = $state<Taste | null>(null);
  let problem = $state<string | null>(null);

  $effect(() => {
    fetchTaste()
      .then((t) => (taste = t))
      .catch((e) => (problem = e instanceof Unreachable ? 'This needs the Pi, which is out of reach.' : String(e)));
  });

  const FEW = 5;
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const rate = (g: Group) => (g.seen ? g.kept / g.seen : 0);

  // One scale for every section, so bars compare across the page.
  const scale = $derived.by(() => {
    if (!taste) return 1;
    const all = [...taste.rooms, ...taste.centuries, ...taste.kinds, ...taste.highlights].filter((g) => g.seen >= FEW);
    const top = Math.max(0.1, ...all.map(rate));
    return Math.ceil(top * 10) / 10;
  });

  const topShare = $derived(taste ? Math.max(0.05, ...taste.steering.rooms.map((r) => r.share)) : 1);

  const oneIn = $derived(taste && taste.kept ? Math.round(taste.seen / taste.kept) : null);

  const usd = (x: number) => `$${x.toFixed(2)}`;
  const cents = (x: number) => (x < 0.1 ? `${(x * 100).toFixed(1)}¢` : usd(x));

  const sections = $derived(
    taste
      ? [
          { title: 'By room', rows: taste.rooms },
          { title: 'By century', rows: taste.centuries },
          { title: 'By kind', rows: taste.kinds },
          { title: 'Highlights', rows: taste.highlights }
        ]
      : []
  );
</script>

<section class="taste" aria-labelledby="taste-title">
  <a class="back" href="#/hoard">Back to the hoard</a>
  <h1 id="taste-title">What you keep</h1>

  {#if problem}
    <p class="lede">{problem}</p>
  {:else if !taste}
    <p class="lede">Counting…</p>
  {:else if taste.seen === 0}
    <p class="lede">Nothing to go on yet. Keep and pass a few pieces and this fills in.</p>
  {:else}
    <p class="lede">
      {taste.kept} kept from {taste.seen} seen{#if oneIn}, about one in {oneIn}{/if}. Bars show how often you keep what
      you're shown, all on one scale up to {pct(scale)}.
    </p>

    {#if taste.artists.length}
      <p class="artists">
        Kept more than once:
        {#each taste.artists as a, i}{a.name} ({a.kept}){i < taste.artists.length - 1 ? ', ' : '.'}{/each}
      </p>
    {/if}

    <div class="grid">
      {#each sections as s}
        <section>
          <h2>{s.title}</h2>
          <ul>
            {#each s.rows as g}
              <li class:few={g.seen < FEW} title={`${g.name}: kept ${g.kept} of ${g.seen} (${pct(rate(g))})`}>
                <span class="name">{g.name}</span>
                <span class="track" aria-hidden="true">
                  <span class="bar" style:width={`${Math.min(1, rate(g) / scale) * 100}%`}></span>
                </span>
                <span class="count">{g.kept} of {g.seen}</span>
              </li>
            {/each}
          </ul>
        </section>
      {/each}

      <section class="steer">
        <h2>Where new pieces come from</h2>
        <p class="note">
          Rooms you keep more from come up more often. Every open room gets at least 5% of picks, so none is shut out.
        </p>
        <ul>
          {#each taste.steering.rooms as r}
            <li title={`${r.name}: ${pct(r.share)} of new pieces`}>
              <span class="name">{r.name}</span>
              <span class="track" aria-hidden="true"><span class="bar" style:width={`${(r.share / topShare) * 100}%`}></span></span>
              <span class="count">{pct(r.share)}</span>
            </li>
          {/each}
        </ul>
        <p class="note">{pct(taste.steering.highlights)} of picks come from the Met's own highlights.</p>
      </section>
    </div>
    <p class="note">Faded rows have fewer than {FEW} pieces behind them: too few to say much.</p>

    <section class="spend" aria-labelledby="spend-title">
      <h2 id="spend-title">What tagging costs</h2>
      {#if taste.spend.calls}
        <p>
          <span class="figure">{usd(taste.spend.month_usd)}</span> this month,
          <span class="figure">{usd(taste.spend.total_usd)}</span> in all, about
          <span class="figure">{cents(taste.spend.per_piece_usd ?? 0)}</span> for each piece Claude tags.
        </p>
        <p class="note">
          Only keeps are tagged, so passing costs nothing. Worked out from Anthropic's list prices and the tokens each
          call used; the bill in the Anthropic Console is the final word.
        </p>
      {:else}
        <p class="note">Nothing yet. Claude tags each piece you keep, for a couple of cents.</p>
      {/if}
    </section>
  {/if}
</section>

<style>
  .taste {
    padding: 4px var(--gutter) 64px;
    max-width: 1100px;
    margin: 0 auto;
  }

  .back {
    font-size: 15px;
    color: var(--on-wall-soft);
    text-underline-offset: 3px;
  }

  h1 {
    font-family: var(--serif);
    font-weight: 400;
    font-size: clamp(36px, 5vw, 56px);
    line-height: 1.05;
    margin: 18px 0 10px;
  }

  .lede {
    color: var(--on-wall-soft);
    max-width: 62ch;
    margin: 0;
  }

  .artists {
    font-family: var(--serif);
    font-size: 17px;
    margin: 16px 0 0;
    max-width: 62ch;
  }

  @media (max-width: 520px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 36px 48px;
    margin-top: 36px;
  }

  h2 {
    font-family: var(--serif);
    font-weight: 500;
    font-size: 19px;
    margin: 0 0 10px;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  li {
    display: grid;
    grid-template-columns: minmax(0, 15em) minmax(60px, 1fr) 4.5em;
    align-items: center;
    gap: 12px;
    padding: 5px 0;
    font-size: 14.5px;
  }

  li.few {
    opacity: 0.5;
  }

  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .track {
    height: 6px;
    background: var(--on-wall-faint);
    border-radius: 0 4px 4px 0;
    overflow: hidden;
  }

  .bar {
    display: block;
    height: 100%;
    background: var(--on-wall);
    border-radius: 0 4px 4px 0;
  }

  .count {
    text-align: right;
    color: var(--on-wall-soft);
    font-variant-numeric: tabular-nums;
  }

  .note {
    color: var(--on-wall-soft);
    font-size: 14px;
    margin: 10px 0 0;
    max-width: 60ch;
  }

  .spend {
    margin-top: 48px;
    padding-top: 20px;
    border-top: 1px solid var(--on-wall-faint);
    max-width: 62ch;
  }

  .spend p {
    margin: 0;
  }

  .spend .note {
    margin-top: 8px;
  }

  .figure {
    font-family: var(--serif);
    font-size: 22px;
    font-variant-numeric: tabular-nums;
  }

  .steer .note:first-of-type {
    margin: 0 0 10px;
  }
</style>
