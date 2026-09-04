# Spor Toto Karar Politikası

Bu dosya, kupon üretirken kullanılacak ana kuralları özetler. Amaç 15 maçı körlemesine kapatmak değil, gerçek oynanabilir kupondan gelir üretme ihtimalini artırmak ve analiz başarısını tek/doğru çift tercihleriyle ölçmektir.

## 1. Birincil ürün dar kupondur

Bundan sonra ana değerlendirme sırası şöyledir:

1. **Dar kupon:** Gerçek parayla oynanan ana kupon. Haftalık performansın birincil ölçüsüdür.
2. **Geniş kupon:** Sanal takip ve kalibrasyon kuponu. Dar kuponun üzerine ek ihtimaller taşıyan kontrol aracıdır.

Geniş kupon 15 bilse bile doğrudan gelir üretmez. Bu yüzden başarı raporunda önce dar kuponun sonucu, sonra geniş kuponun neyi önceden radarına aldığı değerlendirilir.

## 2. Üçlü tercih yok

`1X2` artık kullanılmaz.

Geçerli tercihler:

- `1`
- `X`
- `2`
- `1X`
- `X2`
- `12`

Sebep: `1X2` maç sonucunu otomatik kapsar; bu nedenle analiz başarısı sayılmaz ve kolon verimliliğini düşürür.

## 3. Dar kupon hedefi

Ana hedef:

```text
7-8 çift + kalan maçlar tek = 128-256 kolon
```

Dar kupon geniş kuponun basit kısaltması değildir. Önce gerçek oynanacak dar kupon oluşturulur; risk bütçesi, tek/çift seçimi ve sürpriz dağılımı bu kupon için optimize edilir.

## 4. Geniş kupon hedefi

Geniş kupon dar kuponun üzerine kurulan sanal kontrol kuponudur.

Ana hedef:

```text
Dar kupon + ek ihtimaller → 11 çift + 4 tek = 2.048 kolon
```

Geniş kuponun görevi gelir üretmek değil, dar kuponda alamadığımız ama analizde radarımıza giren ihtimalleri takip etmektir. Hafta sonu değerlendirmesinde şu ayrım yapılır:

| Durum | Anlamı |
|---|---|
| Dar kaçırdı, geniş yakaladı | Daraltma / risk bütçesi hatası |
| Dar kaçırdı, geniş de kaçırdı | Analiz/model hatası |
| Dar yakaladı, geniş de yakaladı | Doğru ana karar |
| Dar yakaladı, geniş kaçırdı | Geniş sanal dağılım hatası |

### Kupon bütünlüğü zorunludur

Hedefler yalnızca uyarı değildir. Bir kuponun `final` veya `oynanabilir` sayılması için:

- dar kupon 7-8 çift ve 128-256 kolon olmalı,
- geniş kupon 11 çift, 2.048 kolon ve en fazla 2.500 kolon olmalı,
- geniş tercih her maçta dar tercihin bütün işaretlerini kapsamalı,
- hiçbir etkin tercihte `1X2` bulunmamalı,
- 15 maçın her birinde geçerli bir seçim bulunmalı.

Kurala aykırı manuel istek sessizce başka bir seçime çevrilmez. İstek denetim kaydında korunur; ilgili kupon `invalid` işaretlenir ve oynanabilir/final olarak sunulmaz. Veri veya karar eksikliği ise `invalid` değil `incomplete` durumudur. Bu kupon denetimi maçların bağımsız model yüzdelerini ve tek/çift adaylarını değiştirmez.

## 5. Türkiye ligi erken sezon kuralı

Ağustos ve eylül döneminde Türkiye maçlarında şu kural uygulanır:

```text
Büyük takım dışı favori %50-58 bandındaysa tek geçilmez.
```

Büyük takım listesi:

- Galatasaray
- Fenerbahçe
- Beşiktaş
- Trabzonspor

Bu kural, ilk haftalardaki yeni kadro uyumu, transfer etkisi, teknik direktör değişimi, reaksiyon maçları ve deplasman sürprizi riskini yükseltmek için kullanılır.

## 6. Tahmin sitesi ve oynanma yüzdesi kullanımı

Tahmin siteleri, Hedef15, Spor Toto yüzdeleri, Nesine, Bilyoner ve Misli dağılımları maç sonucunu kopyalamak için kullanılmaz.

Bu veriler şu amaçlarla kullanılır:

- konsensüs sinyali,
- tuzak favori alarmı,
- düşük yüzdeli ama mantıklı ters tarafı yaşatma,
- kolon dağılımı denetimi.

Kaynak bazlı veriler `data/external_predictions.csv` dosyasına her maç ve kaynak için ayrı satır olarak girilir. Yüzde yayımlamayan sitelerin tercihi yapay yüzdeye çevrilmez; yalnızca yön, uyum ve tuzak sinyali olarak kullanılır. Tam 1-X-2 dağılımı veren bağımsız kaynaklar aşağıdaki ağırlık sınırları içinde modele katılır. Bu satırlar otomatik olarak `data/consensus.csv` içindeki maç bazlı `external_*` özetlerine dönüştürülür.

Yorum metinleri aynen kopyalanmaz. Yalnızca kadro, ceza, form, fikstür yoğunluğu, oyun yapısı veya piyasa gibi doğrulanabilir gerekçelerin kısa özeti; kaynak adı, bağlantısı ve tarihiyle birlikte saklanır. Aynı kaynağın aynı maç için birden fazla girdisi varsa en güncel satır kullanılır.

Kaynaklar iki ayrı grupta değerlendirilir:

| Grup | Kullanım | Karara etkisi |
|---|---|---|
| Spor Toto/Nesine/Bilyoner/Misli oynanma yüzdeleri | Kitle davranışı, tuzak favori ve düşük yüzdeli değer sinyali | Ana olasılığa doğrudan oy çokluğu olarak eklenmez |
| Hedef15 ve diğer bağımsız tahmin modelleri | Bağımsız model konsensüsü | Bir kaynak varsa en fazla %15, iki veya daha fazla kaynak varsa en fazla %25 |

Aynı resmî oynanma dağılımını tekrar eden bayi siteleri bağımsız dört model sayılmaz. Tahmin sitesi verisinin tarihi ve kaynağı kaydedilir; eski haftaya ait veri yeni kupona taşınmaz. Yorum metinleri yalnızca gerekçesi doğrulanabiliyorsa (kadro, ceza, form, fikstür yoğunluğu gibi) karar notuna girer.

## 7. Form, H2H ve takım analizi

Her yeni haftada, kupondaki Süper Lig ve Avrupa takımları için maç tarihinden önce oynanmış verilerle şu özet yeniden hesaplanır:

- takımın son 5 maç formu,
- ev sahibinin iç saha ve deplasman takımının dış saha performansı,
- iki takım arasındaki en fazla son 10 maç,
- H2H galibiyet/beraberlik/mağlubiyet ve gol dağılımı,
- sakatlık, ceza, rotasyon, teknik direktör ve fikstür yoğunluğu,
- önceki haftanın takım gözlemlerinin yeni sonuçlarla doğrulanıp doğrulanmadığı.

H2H tek başına seçim yaptırmaz. İlk 5-6 haftada transfer ve teknik ekip değişiklikleri nedeniyle düşük ağırlıkta kullanılır; güncel form, kadro ve piyasa sinyaliyle aynı yöndeyse güçlenir. Sistem geçmiş maçları yalnızca hedef maçtan önceki tarihten alır; gelecekteki sonuçların modele sızmasına izin verilmez.

## 8. Her maç için zorunlu karar soruları

Her maçta şu sorular cevaplanmalıdır:

1. Bu maç dar kuponda tek geçilebilir mi?
2. Tek geçilmezse dar kupon için doğru çift hangisi?
3. Düşük yüzdeli ama yaşatılması gereken taraf var mı?
4. Favori neden puan kaybeder?
5. Geniş sanal kuponda dar kupona hangi ek ihtimal eklenmeli?
6. Bağımsız modeller ana modelle aynı yönde mi, yoksa anlamlı biçimde ayrışıyor mu?
7. Son 5 maç ve H2H aynı sinyali mi veriyor; H2H güncel kadroyu temsil edecek kadar anlamlı mı?

## 9. Dar kupondan geniş kupona geçiş

Sıra değiştirilemez:

1. Önce 128-256 kolonluk gerçek dar kupon kurulur.
2. Dar kupondaki hiçbir işaret geniş kuponda silinmez.
3. Genişe eklenecek ikinci işaret; risk puanı, bağımsız model ayrışması, tuzak favori, son form ve H2H gerekçelerinden en az biriyle açıklanır.
4. Geniş kupon 11 çift + 4 tek = 2.048 kolon hedefinde sanal kontrol kuponu olarak tamamlanır.
5. Üçlü `1X2` hiçbir aşamada kullanılmaz.

### Olasılık ve dağılım denetimi

- Tek seçim, olasılığı en yüksek sonuçtur.
- Çift seçim, olasılığı en yüksek iki sonuçtur; `1X`, `X2` ve `12` eşit adaydır. X sonucuna otomatik güvenlik önceliği verilmez.
- Ana model çiftinden veya tekinden sapma ancak kadro, piyasa, H2H ya da takım karakteri gerekçesi yazılmışsa korunur. Gerekçesiz manuel sapma reddedilir.
- Her kuponda model yüzdelerinden beklenen 1-X-2 sonuç sayısı ve kuponun kapsadığı 1-X-2 işaret sayısı ayrıca hesaplanır.
- Beklenen X ve 2 sayıları arasındaki fark 0,75 maçtan az olduğu hâlde kapsama farkı 4 veya daha fazlaysa dağılım alarmı verilir.
- Sabit 5-5-5 veya benzeri yapay kota uygulanmaz; haftanın maç yapısı esas alınır.

## 10. Haftalık çalışma döngüsü

- Pazartesi: resmî yeni liste geldiyse yalnızca liste doğrulanır; eski haftanın verisi yeni hafta gibi kullanılmaz.
- Salı: son hafta sonuçları işlenir; takım notları, son 5 form ve H2H özeti yenilenir; ilk dar taslak üretilir.
- Çarşamba ve perşembe: bağımsız tahmin modelleri, oynanma yüzdeleri, oran hareketi, kadro ve haberlerle dar kupon yeniden kalibre edilir.
- Cuma: önce gerçek dar kupon, sonra sanal geniş kupon kesinleştirilir.
- Cumartesi, pazar ve pazartesi: yeni tahmin üretilmez; cuma günü oynanan dar kupon ve sanal geniş kupon takip edilir.
- Salı: yeni kupon haftası başlar.

## 11. Kalibrasyon ölçümü

Hafta sonunda başarı şu sırayla ölçülür:

1. Dar kupon gerçek başarı oranı.
2. Dar kupondaki tek başarı oranı.
3. Dar kupondaki çift başarı oranı.
4. Dar kuponun yanlış sildiği ihtimaller.
5. Geniş sanal kuponun yakaladığı ama dara taşınmayan ihtimaller.
6. Türkiye / Avrupa ayrı performans.
7. Tuzak favori başarı/hata tablosu.
8. Kolon verimliliği.
9. Bağımsız model konsensüsünün katkısı ve yanılttığı maçlar.
10. H2H/form katkısı; eski H2H'nin yanıltıcı olduğu maçlar.

Sonradan yapılan tahmin revizyonları başarı hesabına katılmaz. Cuma günü oynanan dar kupon gerçek referans, geniş kupon sanal/model referansı olarak ayrı değerlendirilir.
