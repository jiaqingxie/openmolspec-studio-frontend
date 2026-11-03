import Head from "next/head";
export default function Home() {
  return (
    <>
      <Head>
        <title>molspec · 你的分子研究伙伴</title>
        <meta
          name="description"
          content="画下分子结构、上传光谱，和 molspec 一起探索分子与光谱。"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/molspec-mark.svg" type="image/svg+xml" />
      </Head>
    </>
  );
}
