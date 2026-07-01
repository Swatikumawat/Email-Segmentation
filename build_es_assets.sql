CREATE OR REPLACE TABLE MODEL_DEV.RAW_MKTO.ES_EMAIL_ASSETS CLONE MODEL_DEV.RAW_MKTO.EMAIL_ASSETS_RAW;

ALTER TABLE MODEL_DEV.RAW_MKTO.ES_EMAIL_ASSETS ADD COLUMN
  PROGRAM_NAME VARCHAR, SEND_NO NUMBER(5,0), ASSET_TYPE VARCHAR;

INSERT INTO MODEL_DEV.RAW_MKTO.ES_EMAIL_ASSETS
  (ASSET_ID, SUBJECT, FROM_NAME, FROM_EMAIL, ATTRIBUTES, _INGESTED_AT, PROGRAM_NAME, SEND_NO, ASSET_TYPE)
SELECT ASSET_ID, subject_base || ' (' || send_no || ')', 'Transmission Marketing', 'hello@transmissionagency.com',
       OBJECT_CONSTRUCT('program', PROGRAM_NAME, 'send_no', send_no), CURRENT_TIMESTAMP(), PROGRAM_NAME, send_no, asset_type
FROM (
  SELECT DISTINCT
    PRIMARY_ATTR_VALUE_ID*100 + ATTRIBUTES:send_no::int AS ASSET_ID,
    PRIMARY_ATTR_VALUE AS PROGRAM_NAME,
    ATTRIBUTES:send_no::int AS send_no,
    CASE PRIMARY_ATTR_VALUE
      WHEN 'Newsletter-Monthly' THEN 'Your monthly roundup'
      WHEN 'Educate-TopOfFunnel' THEN 'A smarter way to get ahead'
      WHEN 'Webinar-Followup-Q2' THEN 'Thanks for joining - your resources'
      WHEN 'Reactivation-90day' THEN 'We miss you - see what is new'
      WHEN 'Case-Study-Healthcare' THEN 'How a peer cut costs 30 percent'
      WHEN 'Welcome-Generic' THEN 'Welcome aboard'
      WHEN 'ROI-Calculator' THEN 'See your potential ROI'
      WHEN 'Demo-Path-T1' THEN 'Ready for a closer look'
      ELSE PRIMARY_ATTR_VALUE END AS subject_base,
    CASE PRIMARY_ATTR_VALUE
      WHEN 'Newsletter-Monthly' THEN 'Newsletter'
      WHEN 'Webinar-Followup-Q2' THEN 'Webinar follow-up'
      WHEN 'Welcome-Generic' THEN 'Onboarding'
      WHEN 'Reactivation-90day' THEN 'Win-back'
      WHEN 'Case-Study-Healthcare' THEN 'Content'
      WHEN 'ROI-Calculator' THEN 'Tool'
      ELSE 'Nurture' END AS asset_type
  FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES
  WHERE ACTIVITY_TYPE_ID=6 AND ATTRIBUTES:send_no IS NOT NULL
);
