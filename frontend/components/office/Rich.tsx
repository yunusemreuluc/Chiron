/** Ajan cevabındaki hafif Markdown: ```kod bloğu```, `satır içi kod`, **kalın**. HTML üretmez
 *  (innerHTML yok) — metin React düğümü olarak kalır. Komuta ve Gözetim'in "Sor" kutusu kullanır. */
export function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(```[\s\S]*?```)/g).map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```') && part.length >= 6) {
          const body = part.slice(3, -3).replace(/^[\w+-]*\n/, '');
          return (
            <pre key={i} className="komuta-code">
              {body}
            </pre>
          );
        }
        return part.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((bit, j) => {
          if (bit.startsWith('`') && bit.endsWith('`') && bit.length > 2)
            return <code key={`${i}-${j}`}>{bit.slice(1, -1)}</code>;
          if (bit.startsWith('**') && bit.endsWith('**') && bit.length > 4)
            return <strong key={`${i}-${j}`}>{bit.slice(2, -2)}</strong>;
          return bit;
        });
      })}
    </>
  );
}
