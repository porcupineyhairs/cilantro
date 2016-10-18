<?php
class testdata extends journal {
	function createFrontPage($article, $issue) {

		//error_reporting(E_ALL);
		//ini_set('display_errors', 1);
		
		$this->setDefaultMetadata($article, $issue);

		$this->metadata['journal_title'] =	strtoupper('Test Magazine');
		$this->metadata['journal_sub'] =	'Mitteilungen der Kommission für alte Geschichte und Epigraphik des Deutschen Archäologischen Instituts';

		$this->metadata['journal_info'] =
"<p>Der CHIRON wird jahrgangsweise und in Leinen gebunden ausgeliefert.<br>
Bestellungen nehmen alle Buchhandlungen entgegen.</p>
<p>Verlag: Walter de Gruyter GmbH, Berlin/Boston<br>
Druck und buchbinderische Verarbeitung: Hubert & Co. GmbH & Co. KG, Göttingen<br>
Anschrift der Redaktion: Kommission für Alte Geschichte und Epigraphik des<br>
Deutschen Archäologischen Instituts, Amalienstr. 73b, 80799 MÜNCHEN, DEUTSCHLAND<br>
redaktion.chiron@dainst.de<p>
<p>Online-Ausgabe: <a href='https://journals.dainst.org/chiron'>https://journals.dainst.org/chiron</a></p>";
				
		
		$pdf = $this->createPDF();
		
		$pdf->daiFrontpage(); // default frontpage layout
		
		$path = $this->settings['tmp_path'] . '/' . md5($article->title->value->value) . '.pdf';
		
		$pdf->Output($path, 'F');
		
		return $path;
		
	}
}
?>