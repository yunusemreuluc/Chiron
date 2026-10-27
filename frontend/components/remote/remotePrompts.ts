// Boş ekran: "ne sorabilirim" sorusunun cevabı hazır istemler olarak duruyor.
// Hepsi Chiron'un GERÇEKTEN uzaktan yapabildiği işler (Notes/Araclar/).
export const REMOTE_PROMPTS: { title: string; hint: string; text: string }[] = [
  {
    title: 'Ekranda ne var?',
    hint: 'Açık pencereye bakar',
    text: 'PC ekranıma bak: şu an ne açık, ne oluyor, bir şey bitmiş ya da hata vermiş mi? Kısaca söyle.',
  },
  {
    title: 'Sistem durumu',
    hint: 'CPU · RAM · disk · pil',
    text: 'PC’nin sistem durumunu kısaca özetle: CPU, RAM, disk ve pil.',
  },
  {
    title: 'Bildirimler',
    hint: 'Son Windows bildirimleri',
    text: 'Son Windows bildirimlerimi oku, önemli bir şey var mı?',
  },
  {
    title: 'Bitince haber ver',
    hint: 'Ekranı izlemeye alır',
    text: 'Ekranda şu an süren işi izle, bittiğinde ya da hata verdiğinde bana haber ver.',
  },
];

