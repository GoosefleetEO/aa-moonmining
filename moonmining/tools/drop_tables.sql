-- Deletes all moonmining tables from the database
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS moonmining_extraction;
DROP TABLE IF EXISTS moonmining_extractionproduct;
DROP TABLE IF EXISTS moonmining_miningledgerrecord;
DROP TABLE IF EXISTS moonmining_moon;
DROP TABLE IF EXISTS moonmining_moonproduct;
DROP TABLE IF EXISTS moonmining_notification;
DROP TABLE IF EXISTS moonmining_owner;
DROP TABLE IF EXISTS moonmining_refinery;
SET FOREIGN_KEY_CHECKS=1;
